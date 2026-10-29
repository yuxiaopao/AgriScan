"""Plot mutations on objects already authorized by a personal or admin route."""
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from PIL import ImageOps
from sqlalchemy import update

from .admin_models import add_audit
from .db import Detection, Plot, PlotDetails
from .ownership import image_referenced

logger = logging.getLogger(__name__)


def remove_unreferenced_image(db, upload_dir, filename):
    folder = Path(upload_dir).resolve()
    target = (folder / filename).resolve()
    if target.parent != folder or image_referenced(db, filename):
        return
    try:
        target.unlink(missing_ok=True)
    except OSError:
        logger.warning('Could not remove unreferenced image %s.', target.name, exc_info=True)


def create_plot(db, body, owner_id, actor):
    plot = Plot(owner_id=owner_id, **body.model_dump(exclude={'latitude', 'longitude', 'owner_id'}))
    if body.latitude is not None:
        plot.details = PlotDetails(latitude=body.latitude, longitude=body.longitude)
    db.add(plot)
    db.flush()
    add_audit(db, actor, 'create', 'plot', plot.id, f'新建地块：{plot.name}')
    db.commit()
    return plot


def update_plot(db, plot, body, actor):
    # Ownership changes require the administrative route's separate validation.
    changes = body.model_dump(exclude_unset=True, exclude={'latitude', 'longitude', 'owner_id'})
    if changes.get('crop', plot.crop) != plot.crop and plot.detections:
        raise HTTPException(409, '地块已有检测记录，不能更改作物类型。')
    for key, value in changes.items():
        setattr(plot, key, value)
    if 'latitude' in body.model_fields_set:
        if not plot.details:
            plot.details = PlotDetails()
        plot.details.latitude = body.latitude
        plot.details.longitude = body.longitude
    add_audit(db, actor, 'update', 'plot', plot.id, f'更新地块：{plot.name}')
    db.commit()
    return plot


async def upload_cover(db, plot, file, actor, upload_dir, max_bytes, read_image):
    original = await read_image(file, max_bytes)
    normalized = ImageOps.exif_transpose(original).convert('RGB')
    normalized.thumbnail((1600, 1600))
    filename = f'{uuid4().hex}.jpg'
    target = Path(upload_dir) / filename
    old_filename = plot.details.cover_filename if plot.details else None
    try:
        normalized.save(target, format='JPEG', quality=90)
        if not plot.details:
            plot.details = PlotDetails()
        plot.details.cover_filename = filename
        add_audit(db, actor, 'update_cover', 'plot', plot.id, f'更新地块封面：{plot.name}')
        db.commit()
    except Exception:
        db.rollback()
        remove_unreferenced_image(db, upload_dir, filename)
        raise
    if old_filename:
        remove_unreferenced_image(db, upload_dir, old_filename)
    return plot


def delete_cover(db, plot, actor, upload_dir):
    filename = plot.details.cover_filename if plot.details else None
    if filename:
        plot.details.cover_filename = None
        add_audit(db, actor, 'delete_cover', 'plot', plot.id, f'移除地块封面：{plot.name}')
        db.commit()
        remove_unreferenced_image(db, upload_dir, filename)
    return plot


def delete_plot(db, plot, actor, upload_dir):
    filename = plot.details.cover_filename if plot.details else None
    db.execute(update(Detection).where(Detection.plot_id == plot.id).values(plot_id=None))
    add_audit(db, actor, 'delete', 'plot', plot.id, f'删除地块并保留历史检测：{plot.name}')
    db.delete(plot)
    db.commit()
    if filename:
        remove_unreferenced_image(db, upload_dir, filename)
    return {'message': '地块已删除，历史检测记录已保留。'}
