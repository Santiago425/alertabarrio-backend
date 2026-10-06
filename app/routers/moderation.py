"""Panel de moderacion: COLA DE PRIORIDAD + PILA para deshacer."""

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import SessionLocal, get_db
from ..security import require_moderator
from ..serializers import report_out, reports_in_order
from ..services import report_service
from ..services.engine import engine

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])


def _dispatch_in_background() -> None:
    db = SessionLocal()
    try:
        report_service.dispatch_notifications(db)
    finally:
        db.close()


@router.get("/queue")
def moderation_queue(db: Session = Depends(get_db), _: models.User = Depends(require_moderator)):
    """Reportes pendientes en el orden EXACTO en que saldran del heap."""
    ordered = engine.queue_order()
    return {
        "size": len(ordered),
        "reports": reports_in_order(db, [r.id for r in ordered]),
        "heap_array": [{"priority": p, "id": i} for p, i in engine.moderation_queue.heap_array()],
    }


@router.get("/in-review", response_model=List[schemas.ReportOut])
def in_review(db: Session = Depends(get_db), _: models.User = Depends(require_moderator)):
    rows = db.scalars(
        select(models.Report).where(models.Report.status == "in_review").order_by(models.Report.priority_score.desc())
    ).unique().all()
    return [report_out(r) for r in rows]


@router.post("/next", response_model=schemas.ReportOut)
def take_next(db: Session = Depends(get_db), moderator: models.User = Depends(require_moderator)):
    """POP de la cola de prioridad: el reporte mas grave pasa a revision."""
    item = engine.take_next()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay reportes pendientes en la cola")
    report = report_service.get_report_or_404(db, item.id)
    report_service.change_status(db, report, "in_review", moderator, "Tomado de la cola de prioridad")
    return report_out(report)


@router.post("/reports/{report_id}/review", response_model=schemas.ReportOut)
def review_specific(report_id: int, db: Session = Depends(get_db), moderator: models.User = Depends(require_moderator)):
    report = report_service.get_report_or_404(db, report_id)
    if report.status != "created":
        raise HTTPException(status.HTTP_409_CONFLICT, "El reporte no esta pendiente")
    engine.take_specific(report_id)  # se saca del heap en O(log n)
    report_service.change_status(db, report, "in_review", moderator, "Abierto directamente por el moderador")
    return report_out(report)


@router.post("/reports/{report_id}/publish")
def publish(
    report_id: int,
    data: schemas.ModerationActionIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    moderator: models.User = Depends(require_moderator),
):
    report = report_service.get_report_or_404(db, report_id)
    if report.status == "created":
        # Se permite publicar directo desde la cola: primero pasa por revision
        engine.take_specific(report_id)
        report_service.change_status(db, report, "in_review", moderator, "Revision rapida")
    queued = report_service.publish(db, report, moderator, data.note)
    background.add_task(_dispatch_in_background)
    return {"report": report_out(report), "notifications_queued": queued}


@router.post("/reports/{report_id}/reject", response_model=schemas.ReportOut)
def reject(
    report_id: int,
    data: schemas.ModerationActionIn,
    db: Session = Depends(get_db),
    moderator: models.User = Depends(require_moderator),
):
    report = report_service.get_report_or_404(db, report_id)
    if report.status == "created":
        engine.take_specific(report_id)
    report_service.change_status(db, report, "rejected", moderator, data.note or "Reporte rechazado")
    return report_out(report)


@router.post("/reports/{report_id}/undo", response_model=schemas.UndoOut)
def undo(
    report_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_moderator),
):
    """DESHACER: pop de la pila de estados del reporte."""
    report = report_service.get_report_or_404(db, report_id)
    undone, current = report_service.undo(db, report)
    background.add_task(_dispatch_in_background)
    db.refresh(report)
    return schemas.UndoOut(
        report=report_out(report),
        undone_status=undone,
        current_status=current,
        stack=[schemas.StatusEntryOut(**e.to_dict()) for e in engine.status_stack(report_id)],
    )
