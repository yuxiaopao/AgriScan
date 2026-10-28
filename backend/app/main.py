import io
import logging
import warnings
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import selectinload

from .extensions import install_extensions, admin_user
from .cache import DashboardCache
from .config import Settings
from .db import Base, Detection, DetectionPrediction, Plot, PlotDetails, RevokedToken, User, make_database, utcnow
from .inference import CROP_COLORS, create_provider, SUPPORTED_CROPS
from .schemas import LoginBody, PlotCreate, PlotUpdate
from .security import current_user, hash_password, issue_token, readable, verify_password
from .seed import KNOWLEDGE, initialize_data

VALID_STATUSES = {"healthy", "attention", "awaiting_model", "queued", "processing", "failed"}
logger = logging.getLogger(__name__)


def remove_unreferenced_image(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Files may remain open while a browser is reading them on Windows.
        # The committed database reference determines whether they are served.
        logger.warning("Could not remove unreferenced image %s.", path.name, exc_info=True)


async def read_uploaded_image(file, max_bytes):
    raw = await file.read(max_bytes + 1)
    await file.close()
    if len(raw) > max_bytes:
        raise HTTPException(413, "图片大小不能超过 10 MB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(422, "仅支持 JPEG、PNG、WebP 图片。")
            if image.width * image.height > 25_000_000:
                raise HTTPException(422, "图片分辨率过大，请压缩至 2500 万像素以内。")
            image.verify()
            # Re-encode decoded pixels to reject corrupt payloads and strip metadata.
            normalized = Image.open(io.BytesIO(raw))
            normalized.load()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "文件不是有效图片，或图片已损坏。")
    return normalized


def detection_data(row):
    return {
        "id": row.id, "name": row.name, "crop": row.crop, "plot_id": row.plot_id,
        "plot_name": row.plot.name if row.plot else "未关联地块", "status": row.status,
        "result": row.result, "confidence": row.confidence,
        "candidates": row.prediction.candidates if row.prediction else [],
        "prediction_model": row.prediction.model if row.prediction else None,
        "created_at": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
        "image_url": row.image_url, "is_demo": row.is_demo, "note": row.note,
    }


def plot_data(plot):
    completed = [d for d in plot.detections if d.status in {"healthy", "attention"}]
    healthy = sum(d.status == "healthy" for d in completed)
    return {
        "id": plot.id, "name": plot.name, "crop": plot.crop, "area": plot.area,
        "location": plot.location, "manager": plot.manager,
        "cover_url": f"/api/uploads/{plot.details.cover_filename}" if plot.details and plot.details.cover_filename else None,
        "latitude": plot.details.latitude if plot.details else None,
        "longitude": plot.details.longitude if plot.details else None,
        "health_score": round(healthy / len(completed) * 100) if completed else None,
        "detections": len(plot.detections),
    }


def create_app(settings=None):
    settings = settings or Settings()
    settings.validate()
    engine, session_factory = make_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(engine)
        with session_factory() as db:
            initialize_data(db, settings)
            db.execute(delete(RevokedToken).where(RevokedToken.expires_at < utcnow()))
            db.commit()
        app.state.cache.invalidate()
        yield
        app.state.cache.close()
        engine.dispose()

    app = FastAPI(title="禾观 AgriScan API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session = session_factory
    app.state.engine = engine
    app.state.cache = DashboardCache(settings.redis_url)
    app.state.inference = create_provider(settings)
    app.state.login_attempts = {}
    app.state.dummy_password_hash = hash_password("dummy-password-for-timing-safety")
    app.add_middleware(
        CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins if x.strip()],
        allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def get_db():
        with session_factory() as db:
            yield db

    def load_detection(db, detection_id):
        row = db.scalar(select(Detection).options(selectinload(Detection.plot)).where(Detection.id == detection_id))
        if not row:
            raise HTTPException(404, "未找到检测记录。")
        return row

    @app.get("/api/health")
    def health(db=Depends(get_db)):
        database = "connected"
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            database = "unavailable"
        redis_state = app.state.cache.status()
        return {
            "status": "ok" if database == "connected" and redis_state != "unavailable" else "degraded",
            "database": database, "redis": redis_state,
            "mode": "demo" if settings.demo_mode else "production",
            "model": app.state.inference.status,
        }

    @app.post("/api/auth/login")
    def login(body: LoginBody, request: Request, db=Depends(get_db)):
        # Small process-local abuse guard; a gateway limit is recommended across workers.
        host = request.client.host if request.client else "unknown"
        key = (host, body.username)
        now = datetime.now(timezone.utc).timestamp()
        attempts = [t for t in app.state.login_attempts.get(key, []) if now - t < 300]
        if len(attempts) >= 10:
            raise HTTPException(429, "登录尝试过于频繁，请 5 分钟后重试。")
        user = db.scalar(select(User).where(User.username == body.username))
        valid = verify_password(body.password, user.password_hash if user else app.state.dummy_password_hash)
        if not user or not valid:
            app.state.login_attempts[key] = attempts + [now]
            raise HTTPException(401, "用户名或密码错误。")
        app.state.login_attempts.pop(key, None)
        return {
            "access_token": issue_token(user, settings), "token_type": "bearer",
            "user": {"name": user.name, "role": user.role, "username": user.username},
        }

    @app.get("/api/auth/me")
    def me(user=Depends(current_user)):
        return {"name": user.name, "role": user.role, "username": user.username}

    @app.post("/api/auth/logout")
    def logout(request: Request, user=Depends(current_user), db=Depends(get_db)):
        payload = request.state.token_payload
        db.merge(RevokedToken(
            jti=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc).replace(tzinfo=None),
        ))
        db.commit()
        return {"message": "已安全退出登录。"}

    @app.get("/api/dashboard", dependencies=[Depends(readable)])
    def dashboard(days: int = Query(default=7), db=Depends(get_db)):
        if days not in (7, 30):
            raise HTTPException(422, "统计周期仅支持 7 天或 30 天。")
        cached = app.state.cache.get(days)
        if cached is not None:
            return cached
        counts = dict(db.execute(select(Detection.status, func.count()).group_by(Detection.status)).all())
        total = sum(counts.values())
        local_timezone = timezone(timedelta(hours=8))
        end_date = datetime.now(local_timezone).date()
        start = datetime.combine(
            end_date - timedelta(days=days - 1), datetime.min.time(), tzinfo=local_timezone,
        ).astimezone(timezone.utc).replace(tzinfo=None)
        recent_period = db.scalars(select(Detection).where(Detection.created_at >= start)).all()
        daily_counts = {}
        for row in recent_period:
            day = row.created_at.replace(tzinfo=timezone.utc).astimezone(local_timezone).date()
            if day not in daily_counts:
                daily_counts[day] = {"total": 0, "healthy": 0}
            daily_counts[day]["total"] += 1
            daily_counts[day]["healthy"] += row.status == "healthy"
        trend = []
        for offset in range(days):
            day = end_date - timedelta(days=days - 1 - offset)
            trend.append({"label": day.strftime("%m/%d"), **daily_counts.get(day, {"total": 0, "healthy": 0})})
        by_crop = dict(db.execute(select(Detection.crop, func.count()).group_by(Detection.crop)).all())
        recent = db.scalars(
            select(Detection).options(selectinload(Detection.plot)).order_by(Detection.created_at.desc()).limit(5)
        ).all()
        data = {
            "stats": {
                "total": total, "healthy": counts.get("healthy", 0), "attention": counts.get("attention", 0),
                "pending": sum(counts.get(s, 0) for s in ["awaiting_model", "queued", "processing"]),
            },
            "trend": trend,
            "distribution": [
                {"name": crop, "value": by_crop.get(crop, 0), "color": CROP_COLORS.get(crop, "#78a477")}
                for crop in SUPPORTED_CROPS if by_crop.get(crop, 0)
            ],
            "recent": [detection_data(row) for row in recent],
            "is_demo": settings.demo_mode,
        }
        app.state.cache.set(data, days)
        return data

    @app.get("/api/detections", dependencies=[Depends(readable)])
    def detections(
        search: str = Query(default="", max_length=100),
        crop: str = "", status: str = "", db=Depends(get_db),
    ):
        if crop and crop not in SUPPORTED_CROPS:
            raise HTTPException(422, "暂不支持该作物。")
        if status and status not in VALID_STATUSES:
            raise HTTPException(422, "无效的检测状态。")
        query = select(Detection).options(selectinload(Detection.plot))
        if crop:
            query = query.where(Detection.crop == crop)
        if status:
            query = query.where(Detection.status == status)
        if search.strip():
            query = query.where(or_(
                Detection.name.contains(search.strip(), autoescape=True),
                Detection.crop.contains(search.strip(), autoescape=True),
                Detection.result.contains(search.strip(), autoescape=True),
            ))
        return [detection_data(row) for row in db.scalars(query.order_by(Detection.created_at.desc())).all()]

    @app.post("/api/detections", status_code=201, dependencies=[Depends(current_user)])
    async def upload(
        file: UploadFile = File(...), crop: str = Form(...), plot_id: str | None = Form(None),
        note: str = Form(default="", max_length=2000), db=Depends(get_db),
    ):
        if crop not in SUPPORTED_CROPS:
            raise HTTPException(422, "请选择支持的作物类型。")
        plot_id = plot_id or None
        if plot_id:
            plot = db.get(Plot, plot_id)
            if not plot:
                raise HTTPException(404, "关联地块不存在。")
            if plot.crop != crop:
                raise HTTPException(422, "作物类型与所选地块不一致。")
        normalized = (await read_uploaded_image(file, settings.max_upload_bytes)).convert("RGB")
        filename = f"{uuid4().hex}.jpg"
        target = settings.upload_dir / filename
        try:
            normalized.save(target, format="JPEG", quality=90)
            predicted = await run_in_threadpool(app.state.inference.predict, target, crop)
            # Windows and POSIX path components are stripped from client-supplied names.
            display_name = (file.filename or "田间采样").replace("\\", "/").split("/")[-1][:180]
            row = Detection(
                name=display_name, crop=crop, plot_id=plot_id, note=note.strip(),
                status=predicted.status, result=predicted.label, confidence=predicted.confidence,
                image_url=f"/api/uploads/{filename}", is_demo=False,
            )
            if predicted.model:
                row.prediction = DetectionPrediction(candidates=predicted.candidates, model=predicted.model)
            db.add(row)
            db.commit()
        except Exception:
            db.rollback()
            target.unlink(missing_ok=True)
            raise
        app.state.cache.invalidate()
        return detection_data(load_detection(db, row.id))

    @app.get("/api/detections/{detection_id}", dependencies=[Depends(readable)])
    def detection(detection_id: str, db=Depends(get_db)):
        return detection_data(load_detection(db, detection_id))

    @app.delete("/api/detections/{detection_id}", dependencies=[Depends(admin_user)])
    def delete_detection(detection_id: str, db=Depends(get_db)):
        row = load_detection(db, detection_id)
        image_url = row.image_url
        db.delete(row)
        db.commit()
        if image_url and image_url.startswith("/api/uploads/"):
            target = (settings.upload_dir / Path(image_url).name).resolve()
            if target.parent == settings.upload_dir:
                target.unlink(missing_ok=True)
        app.state.cache.invalidate()
        return {"message": "检测记录已删除。"}

    @app.get("/api/uploads/{filename}", dependencies=[Depends(readable)])
    def uploaded_image(filename: str, db=Depends(get_db)):
        if len(filename) != 36 or not filename.endswith(".jpg") or any(c not in "0123456789abcdef" for c in filename[:-4]):
            raise HTTPException(404, "图片不存在。")
        target = settings.upload_dir / filename
        referenced = db.scalar(select(Detection.id).where(Detection.image_url == f"/api/uploads/{filename}"))
        if not referenced:
            referenced = db.scalar(select(PlotDetails.plot_id).where(PlotDetails.cover_filename == filename))
        if not target.is_file() or not referenced:
            raise HTTPException(404, "图片不存在。")
        return FileResponse(target, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/api/plots", dependencies=[Depends(readable)])
    def plots(db=Depends(get_db)):
        return [plot_data(p) for p in db.scalars(select(Plot).options(selectinload(Plot.detections)).order_by(Plot.name))]

    @app.post("/api/plots", status_code=201, dependencies=[Depends(admin_user)])
    def create_plot(body: PlotCreate, db=Depends(get_db)):
        plot = Plot(**body.model_dump(exclude={"latitude", "longitude"}))
        if body.latitude is not None:
            plot.details = PlotDetails(latitude=body.latitude, longitude=body.longitude)
        db.add(plot)
        db.commit()
        app.state.cache.invalidate()
        return plot_data(plot)

    @app.patch("/api/plots/{plot_id}", dependencies=[Depends(admin_user)])
    def update_plot(plot_id: str, body: PlotUpdate, db=Depends(get_db)):
        plot = db.get(Plot, plot_id)
        if not plot:
            raise HTTPException(404, "地块不存在。")
        changes = body.model_dump(exclude_unset=True, exclude={"latitude", "longitude"})
        if changes.get("crop", plot.crop) != plot.crop and plot.detections:
            raise HTTPException(409, "地块已有检测记录，不能更改作物类型。")
        for key, value in changes.items():
            setattr(plot, key, value)
        if "latitude" in body.model_fields_set:
            if not plot.details:
                plot.details = PlotDetails()
            plot.details.latitude = body.latitude
            plot.details.longitude = body.longitude
        db.commit()
        app.state.cache.invalidate()
        return plot_data(plot)

    @app.post("/api/plots/{plot_id}/cover", dependencies=[Depends(admin_user)])
    async def upload_plot_cover(plot_id: str, file: UploadFile = File(...), db=Depends(get_db)):
        plot = db.get(Plot, plot_id)
        if not plot:
            raise HTTPException(404, "地块不存在。")
        normalized = await read_uploaded_image(file, settings.max_upload_bytes)
        normalized = ImageOps.exif_transpose(normalized).convert("RGB")
        normalized.thumbnail((1600, 1600))
        filename = f"{uuid4().hex}.jpg"
        target = settings.upload_dir / filename
        old_filename = plot.details.cover_filename if plot.details else None
        try:
            normalized.save(target, format="JPEG", quality=90)
            if not plot.details:
                plot.details = PlotDetails()
            plot.details.cover_filename = filename
            db.commit()
        except Exception:
            db.rollback()
            remove_unreferenced_image(target)
            raise
        if old_filename:
            remove_unreferenced_image(settings.upload_dir / old_filename)
        app.state.cache.invalidate()
        return plot_data(plot)

    @app.delete("/api/plots/{plot_id}/cover", dependencies=[Depends(admin_user)])
    def delete_plot_cover(plot_id: str, db=Depends(get_db)):
        plot = db.get(Plot, plot_id)
        if not plot:
            raise HTTPException(404, "地块不存在。")
        cover_filename = plot.details.cover_filename if plot.details else None
        if cover_filename:
            plot.details.cover_filename = None
            db.commit()
            remove_unreferenced_image(settings.upload_dir / cover_filename)
            app.state.cache.invalidate()
        return plot_data(plot)

    @app.delete("/api/plots/{plot_id}", dependencies=[Depends(admin_user)])
    def delete_plot(plot_id: str, db=Depends(get_db)):
        plot = db.get(Plot, plot_id)
        if not plot:
            raise HTTPException(404, "地块不存在。")
        cover_filename = plot.details.cover_filename if plot.details else None
        db.execute(update(Detection).where(Detection.plot_id == plot_id).values(plot_id=None))
        db.delete(plot)
        db.commit()
        if cover_filename:
            remove_unreferenced_image(settings.upload_dir / cover_filename)
        app.state.cache.invalidate()
        return {"message": "地块已删除，历史检测记录已保留。"}

    @app.get("/api/knowledge", dependencies=[Depends(readable)])
    def knowledge():
        return KNOWLEDGE

    install_extensions(app, settings, get_db)
    return app


app = create_app()
