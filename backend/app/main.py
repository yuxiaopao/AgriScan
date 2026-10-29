import io
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
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import selectinload

from .extensions import install_extensions
from .cache import DashboardCache
from .config import Settings
from .db import Detection, DetectionPrediction, Plot, PlotDetails, RevokedToken, User, make_database, utcnow
from .inference import CROP_COLORS, create_provider, SUPPORTED_CROPS, prediction_snapshot, public_prediction_model
from .schemas import LoginBody, PlotCreate, PlotUpdate
from .security import current_user, hash_password, issue_token, readable, verify_password
from .seed import initialize_data
from .admin import install_admin
from .admin_models import KnowledgeArticle, add_audit, article_data, initialize_admin_data
from .migrations import migrate_database
from .media import install_media
from .runtime_config import RuntimeSettings, install_runtime_config
from .ownership import associated_plot, detection_scope, owned_detection, owned_plot, plot_scope
from . import plot_operations
from .inference_scheduler import InferenceScheduler
from .detection_tasks import install_detection_tasks

VALID_STATUSES = {"healthy", "attention", "awaiting_model", "queued", "processing", "failed"}
async def read_uploaded_image(file, max_bytes):
    raw = await file.read(max_bytes + 1)
    await file.close()
    if len(raw) > max_bytes:
        raise HTTPException(413, f"图片大小不能超过 {max_bytes // (1024 * 1024)} MB。")
    return decode_uploaded_image(raw, max_bytes)


def decode_uploaded_image(raw, max_bytes):
    if len(raw) > max_bytes:
        raise HTTPException(413, f"图片大小不能超过 {max_bytes // (1024 * 1024)} MB。")
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
    plot = associated_plot(row)
    return {
        "id": row.id, "name": row.name, "crop": row.crop, "plot_id": plot.id if plot else None,
        "plot_name": plot.name if plot else "未关联地块", "status": row.status,
        "result": row.result, "confidence": row.confidence,
        "candidates": row.prediction.candidates if row.prediction else [],
        "prediction_model": public_prediction_model(row.prediction.model) if row.prediction else None,
        "boxes": row.prediction.model.get('boxes', []) if row.prediction else [],
        "created_at": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
        "image_url": row.image_url, "is_demo": row.is_demo, "note": row.note,
    }


def plot_data(plot, *, administrative=False):
    visible = [row for row in plot.detections if administrative or (
        row.owner_id == plot.owner_id and (plot.owner_id is not None or row.is_demo))]
    completed = [d for d in visible if d.status in {"healthy", "attention"}]
    healthy = sum(d.status == "healthy" for d in completed)
    return {
        "id": plot.id, "name": plot.name, "crop": plot.crop, "area": plot.area,
        "location": plot.location, "manager": plot.manager,
        "cover_url": f"/api/uploads/{plot.details.cover_filename}" if plot.details and plot.details.cover_filename else None,
        "latitude": plot.details.latitude if plot.details else None,
        "longitude": plot.details.longitude if plot.details else None,
        "health_score": round(healthy / len(completed) * 100) if completed else None,
        "detections": len(visible),
    }


def create_app(settings=None):
    settings = settings or Settings()
    settings.validate()
    if not isinstance(settings, RuntimeSettings):
        settings = RuntimeSettings(settings)
    engine, session_factory = make_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        migrate_database(engine)
        app.state.runtime_config.refresh()
        with session_factory() as db:
            initialize_data(db, settings)
            initialize_admin_data(db)
            db.execute(delete(RevokedToken).where(RevokedToken.expires_at < utcnow()))
            db.commit()
        app.state.cache.invalidate()
        app.state.detection_tasks.start()
        try:
            yield
        finally:
            await run_in_threadpool(app.state.email_mailer.close)
            await run_in_threadpool(app.state.detection_tasks.close)
        app.state.cache.close()
        engine.dispose()

    app = FastAPI(title="禾观 AgriScan API", version="1.0.0", lifespan=lifespan)

    @app.middleware('http')
    async def private_api_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'private, no-store'
            vary = [part.strip() for part in response.headers.get('Vary', '').split(',') if part.strip()]
            if 'authorization' not in {part.lower() for part in vary}:
                vary.append('Authorization')
            response.headers['Vary'] = ', '.join(vary)
        return response
    app.state.settings = settings
    app.state.session = session_factory
    app.state.engine = engine
    app.state.cache = DashboardCache(settings.redis_url)
    app.state.inference = create_provider(settings)
    app.state.inference_scheduler = InferenceScheduler()
    app.state.login_attempts = {}
    app.state.dummy_password_hash = hash_password("dummy-password-for-timing-safety")
    def get_db():
        with session_factory() as db:
            yield db

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
        if not user or not user.is_active or not valid:
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
        with app.state.detection_tasks.condition:
            db.merge(RevokedToken(
                jti=payload["jti"],
                expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc).replace(tzinfo=None),
            ))
            db.commit()
            app.state.detection_tasks.cancel_session(payload["jti"])
        return {"message": "已安全退出登录。"}

    @app.get("/api/dashboard")
    def dashboard(days: int = Query(default=7), user=Depends(readable), db=Depends(get_db)):
        if days not in (7, 30):
            raise HTTPException(422, "统计周期仅支持 7 天或 30 天。")
        owner_id = user.id if user else None
        scope = detection_scope(user)
        cached = app.state.cache.get(days, owner_id)
        if cached is not None:
            return cached
        counts = dict(db.execute(select(Detection.status, func.count()).where(scope).group_by(Detection.status)).all())
        total = sum(counts.values())
        local_timezone = timezone(timedelta(hours=8))
        end_date = datetime.now(local_timezone).date()
        start = datetime.combine(
            end_date - timedelta(days=days - 1), datetime.min.time(), tzinfo=local_timezone,
        ).astimezone(timezone.utc).replace(tzinfo=None)
        recent_period = db.scalars(select(Detection).where(scope, Detection.created_at >= start)).all()
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
        by_crop = dict(db.execute(select(Detection.crop, func.count()).where(scope).group_by(Detection.crop)).all())
        recent = db.scalars(
            select(Detection).options(selectinload(Detection.plot)).where(scope).order_by(Detection.created_at.desc()).limit(5)
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
        app.state.cache.set(data, days, owner_id)
        return data

    @app.get("/api/detections")
    def detections(
        search: str = Query(default="", max_length=100),
        crop: str = "", status: str = "", user=Depends(readable), db=Depends(get_db),
    ):
        if crop and crop not in SUPPORTED_CROPS:
            raise HTTPException(422, "暂不支持该作物。")
        if status and status not in VALID_STATUSES:
            raise HTTPException(422, "无效的检测状态。")
        query = select(Detection).options(selectinload(Detection.plot)).where(detection_scope(user))
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

    @app.post("/api/detections", status_code=201)
    async def upload(
        file: UploadFile = File(...), crop: str | None = Form(None), plot_id: str | None = Form(None),
        note: str = Form(default="", max_length=2000), user=Depends(current_user), db=Depends(get_db),
    ):
        crop = (crop or "").strip() or None
        if crop and crop not in SUPPORTED_CROPS:
            raise HTTPException(422, "请选择支持的作物类型。")
        plot_id = plot_id or None
        plot = None
        if plot_id:
            plot = owned_plot(db, plot_id, user)
            if crop and plot.crop != crop:
                raise HTTPException(422, "作物类型与所选地块不一致。")
        async with app.state.inference_scheduler.legacy_processing():
            return await upload_admitted(file, crop, plot_id, note, user, db)

    async def upload_admitted(file, crop, plot_id, note, user, db):
        plot = owned_plot(db, plot_id, user) if plot_id else None
        original = await read_uploaded_image(file, settings.max_upload_bytes)
        try:
            normalized = ImageOps.exif_transpose(original).convert("RGB")
        finally:
            original.close()
        filename = f"{uuid4().hex}.jpg"
        target = settings.upload_dir / filename
        try:
            try:
                normalized.save(target, format="JPEG", quality=90)
            finally:
                normalized.close()
            predicted = await run_in_threadpool(app.state.inference_scheduler.predict, app.state.inference, target, crop)
            identified_crop = crop or predicted.crop
            if identified_crop not in SUPPORTED_CROPS:
                raise HTTPException(503, "模型未返回有效的作物识别结果，请检查模型服务或稍后重试。")
            if plot_id:
                plot = owned_plot(db, plot_id, user, lock=True)
            detected_crops = {box['crop'] for box in predicted.boxes} or {identified_crop}
            if plot and any(found != plot.crop for found in detected_crops):
                crop_summary = '、'.join(sorted(detected_crops))
                raise HTTPException(422, f"检测目标包含{crop_summary}，与所选{plot.crop}地块不一致，请更换地块或取消关联后重试。")
            # Windows and POSIX path components are stripped from client-supplied names.
            display_name = (file.filename or "田间采样").replace("\\", "/").split("/")[-1][:180]
            row = Detection(
                owner_id=user.id,
                name=display_name, crop=identified_crop, plot_id=plot_id, note=note.strip(),
                status=predicted.status, result=predicted.label, confidence=predicted.confidence,
                image_url=f"/api/uploads/{filename}", is_demo=False,
            )
            if predicted.model:
                row.prediction = DetectionPrediction(candidates=predicted.candidates, model=prediction_snapshot(predicted))
            db.add(row)
            db.commit()
        except Exception:
            db.rollback()
            target.unlink(missing_ok=True)
            raise
        app.state.cache.invalidate(user.id)
        return detection_data(owned_detection(db, row.id, user))

    @app.get("/api/detections/{detection_id}")
    def detection(detection_id: str, user=Depends(readable), db=Depends(get_db)):
        return detection_data(owned_detection(db, detection_id, user))

    @app.delete("/api/detections/{detection_id}")
    def delete_detection(detection_id: str, user=Depends(current_user), db=Depends(get_db)):
        row = owned_detection(db, detection_id, user, lock=True)
        image_url = row.image_url
        add_audit(db, user, "delete", "detection", row.id, f"删除检测样本：{row.name}")
        db.delete(row)
        db.commit()
        if image_url and image_url.startswith("/api/uploads/"):
            plot_operations.remove_unreferenced_image(db, settings.upload_dir, Path(image_url).name)
        app.state.cache.invalidate(user.id)
        return {"message": "检测记录已删除。"}

    @app.get("/api/uploads/{filename}")
    def uploaded_image(filename: str, user=Depends(readable), db=Depends(get_db)):
        if len(filename) != 36 or not filename.endswith(".jpg") or any(c not in "0123456789abcdef" for c in filename[:-4]):
            raise HTTPException(404, "图片不存在。")
        target = settings.upload_dir / filename
        referenced = db.scalar(select(Detection.id).where(
            Detection.image_url == f"/api/uploads/{filename}", detection_scope(user)))
        if not referenced:
            referenced = db.scalar(select(PlotDetails.plot_id).join(Plot).where(
                PlotDetails.cover_filename == filename, plot_scope(user)))
        if not target.is_file() or not referenced:
            raise HTTPException(404, "图片不存在。")
        return FileResponse(target, media_type="image/jpeg", headers={
            "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store", "Vary": "Authorization"})

    @app.get("/api/plots")
    def plots(user=Depends(readable), db=Depends(get_db)):
        return [plot_data(p) for p in db.scalars(select(Plot).options(selectinload(Plot.detections))
                                               .where(plot_scope(user)).order_by(Plot.name))]

    @app.post("/api/plots", status_code=201)
    def create_plot(body: PlotCreate, user=Depends(current_user), db=Depends(get_db)):
        plot = plot_operations.create_plot(db, body, user.id, user)
        app.state.cache.invalidate(user.id)
        return plot_data(plot)

    @app.patch("/api/plots/{plot_id}")
    def update_plot(plot_id: str, body: PlotUpdate, user=Depends(current_user), db=Depends(get_db)):
        plot = plot_operations.update_plot(db, owned_plot(db, plot_id, user, lock=True), body, user)
        app.state.cache.invalidate(user.id)
        return plot_data(plot)

    @app.post("/api/plots/{plot_id}/cover")
    async def upload_plot_cover(plot_id: str, file: UploadFile = File(...), user=Depends(current_user), db=Depends(get_db)):
        plot = await plot_operations.upload_cover(db, owned_plot(db, plot_id, user, lock=True), file, user,
                                                  settings.upload_dir, settings.max_upload_bytes, read_uploaded_image)
        app.state.cache.invalidate(user.id)
        return plot_data(plot)

    @app.delete("/api/plots/{plot_id}/cover")
    def delete_plot_cover(plot_id: str, user=Depends(current_user), db=Depends(get_db)):
        plot = plot_operations.delete_cover(db, owned_plot(db, plot_id, user, lock=True), user, settings.upload_dir)
        app.state.cache.invalidate(user.id)
        return plot_data(plot)

    @app.delete("/api/plots/{plot_id}")
    def delete_plot(plot_id: str, user=Depends(current_user), db=Depends(get_db)):
        result = plot_operations.delete_plot(db, owned_plot(db, plot_id, user, lock=True), user, settings.upload_dir)
        app.state.cache.invalidate(user.id)
        return result

    @app.get("/api/knowledge", dependencies=[Depends(readable)])
    def knowledge(db=Depends(get_db)):
        rows = db.scalars(select(KnowledgeArticle).where(KnowledgeArticle.status == "published")
                          .order_by(KnowledgeArticle.created_at, KnowledgeArticle.id)).all()
        fields = ("id", "title", "crop", "category", "summary", "content", "sources", "image")
        return [{key: value for key, value in article_data(row).items() if key in fields} for row in rows]

    install_extensions(app, settings, get_db)
    install_admin(app, get_db, detection_data, plot_data)
    install_media(app, get_db)
    install_detection_tasks(app, decode_uploaded_image)
    install_runtime_config(app, settings, get_db)
    # CORS wraps feature restrictions so native clients can read their errors.
    app.add_middleware(
        CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins if x.strip()],
        allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    return app


app = create_app()
