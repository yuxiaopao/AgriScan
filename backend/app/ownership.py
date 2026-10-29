"""Personal-workspace scopes; administrative routes authorize separately."""
from fastapi import HTTPException
from sqlalchemy import and_, exists, select
from sqlalchemy.orm import selectinload

from .db import Detection, Plot, PlotDetails


def detection_scope(user):
    if user is None:
        return and_(Detection.owner_id.is_(None), Detection.is_demo.is_(True))
    return Detection.owner_id == user.id


def plot_scope(user):
    if user is not None:
        return Plot.owner_id == user.id
    # A null owner alone never makes historical business records public.
    demo_reference = exists(select(Detection.id).where(
        Detection.plot_id == Plot.id, Detection.owner_id.is_(None), Detection.is_demo.is_(True)))
    return and_(Plot.owner_id.is_(None), demo_reference)


def _lock_query(db, query, lock):
    if not lock:
        return query
    if db.bind.dialect.name == 'sqlite':
        connection = db.connection()
        # sqlite3 legacy mode does not start a physical transaction on SELECT.
        # Acquire the writer reservation before checking current ownership.
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
    return query.with_for_update().execution_options(populate_existing=True)


def owned_detection(db, detection_id, user, *, lock=False):
    query = select(Detection).options(selectinload(Detection.plot)).where(
        Detection.id == detection_id, detection_scope(user))
    row = db.scalar(_lock_query(db, query, lock))
    if row is None:
        raise HTTPException(404, '未找到检测记录。')
    return row


def owned_plot(db, plot_id, user, *, lock=False):
    query = select(Plot).where(Plot.id == plot_id, plot_scope(user))
    row = db.scalar(_lock_query(db, query, lock))
    if row is None:
        raise HTTPException(404, '地块不存在。')
    return row


def associated_plot(row):
    """Do not reveal a stale or incorrectly linked foreign owner's plot."""
    plot = row.plot
    return plot if plot is not None and plot.owner_id == row.owner_id else None


def image_referenced(db, filename):
    """File cleanup must preserve any surviving reference, including legacy ones."""
    return (db.scalar(select(Detection.id).where(Detection.image_url == '/api/uploads/' + filename).limit(1))
            or db.scalar(select(PlotDetails.plot_id).where(PlotDetails.cover_filename == filename).limit(1)))
