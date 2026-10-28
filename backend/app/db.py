from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Double, Float, ForeignKey, String, Text, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def new_id():
    return uuid4().hex


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(80), default="农场管理员")
    role: Mapped[str] = mapped_column(String(30), default="admin")


class Plot(Base):
    __tablename__ = "plots"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    crop: Mapped[str] = mapped_column(String(40))
    area: Mapped[float] = mapped_column(Float)
    location: Mapped[str] = mapped_column(String(200))
    manager: Mapped[str] = mapped_column(String(80))
    detections: Mapped[list["Detection"]] = relationship(back_populates="plot", passive_deletes=True)
    details: Mapped["PlotDetails | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin")


class PlotDetails(Base):
    __tablename__ = "plot_details"
    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id", ondelete="CASCADE"), primary_key=True)
    cover_filename: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Double, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Double, nullable=True)


class Detection(Base):
    __tablename__ = "detections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    crop: Mapped[str] = mapped_column(String(40), index=True)
    plot_id: Mapped[str | None] = mapped_column(ForeignKey("plots.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    result: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    plot: Mapped[Plot | None] = relationship(back_populates="detections")
    prediction: Mapped["DetectionPrediction | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin")


class DetectionPrediction(Base):
    """Immutable inference snapshot; a new table preserves existing detection rows."""
    __tablename__ = "detection_predictions"
    detection_id: Mapped[str] = mapped_column(
        ForeignKey("detections.id", ondelete="CASCADE"), primary_key=True)
    candidates: Mapped[list] = mapped_column(JSON)
    model: Mapped[dict] = mapped_column(JSON)


class AppMeta(Base):
    __tablename__ = "app_meta"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(100))


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


def make_database(url):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        path = make_url(url).database
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
