"""
Reportes de seguridad.

Aqui esta el CICLO COMPLETO que pidio el profe:
    Frontend -> Backend (POST /reports) -> guarda en BD -> llama a la IA
    -> la IA clasifica y calcula el riesgo -> Backend guarda el resultado
    en BD -> mete el reporte a la cola de prioridad -> responde al Frontend.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..database import get_db
from ..security import get_current_user
from ..serializers import confirmations_for, report_out, reports_in_order
from ..services import ai_client
from ..services.engine import ReportItem, compute_priority, engine
from ..services.report_service import change_status, get_report_or_404, to_local

router = APIRouter(prefix="/api/v1", tags=["reports"])


def _history_for_ai(db: Session, neighborhood_id: int, exclude_id: int) -> list:
    since = datetime.now(timezone.utc) - timedelta(days=180)
    rows = db.scalars(
        select(models.Report).where(
            models.Report.neighborhood_id == neighborhood_id,
            models.Report.occurred_at >= since,
            models.Report.status != "rejected",
            models.Report.id != exclude_id,
        )
    ).all()
    return [
        {
            "occurred_at": to_local(r.occurred_at).isoformat(),
            "severity": r.incident_type.severity_level,
            "incident_type_code": r.incident_type.code,
        }
        for r in rows
    ]


@router.post("/reports", response_model=schemas.ReportCreatedOut, status_code=201)
def create_report(
    data: schemas.ReportIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    incident_type = db.get(models.IncidentType, data.incident_type_id)
    neighborhood = db.get(models.Neighborhood, data.neighborhood_id)
    if incident_type is None or neighborhood is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de incidente o barrio invalido")
    occurred_at = data.occurred_at or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    if occurred_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha del incidente no puede ser futura")

    # 1) Guardar en base de datos con estado inicial "created"
    report = models.Report(
        user_id=user.id,
        neighborhood_id=neighborhood.id,
        incident_type_id=incident_type.id,
        title=data.title.strip(),
        description=data.description.strip(),
        latitude=data.latitude,
        longitude=data.longitude,
        occurred_at=occurred_at,
        status="created",
        priority_score=compute_priority(incident_type.severity_level, None, bool(data.photo_url)),
    )
    db.add(report)
    db.flush()
    if data.photo_url:
        db.add(models.ReportPhoto(report_id=report.id, url=data.photo_url))
    first = models.ReportStatusHistory(
        report_id=report.id, previous_status=None, new_status="created", changed_by=user.id, note="Reporte creado"
    )
    db.add(first)
    db.flush()

    # 2) Enviar al componente de IA
    ai_payload = {
        "description": f"{report.title}. {report.description}",
        "incident_type_code": incident_type.code,
        "occurred_at": to_local(occurred_at).isoformat(),
        "neighborhood_id": neighborhood.id,
        "history": _history_for_ai(db, neighborhood.id, report.id),
    }
    ai = ai_client.analyze_report(db, ai_payload, report.id, neighborhood.id)

    # 3) Guardar lo que respondio la IA
    ai_out = schemas.AIResultOut(available=ai is not None)
    if ai is not None:
        suggested = db.scalar(select(models.IncidentType).where(models.IncidentType.code == ai.get("suggested_type_code")))
        report.ai_suggested_type_id = suggested.id if suggested else None
        report.ai_confidence = ai.get("confidence")
        report.ai_zone_risk = ai.get("zone_risk")
        # Si la IA esta muy segura de que es algo MAS grave, se usa esa gravedad
        # para la prioridad (ej: el vecino marco "hurto" pero describio un robo con pistola)
        severity = incident_type.severity_level
        if suggested and (report.ai_confidence or 0) >= 0.7:
            severity = max(severity, suggested.severity_level)
        report.priority_score = compute_priority(severity, report.ai_zone_risk, bool(data.photo_url))
        ai_out = schemas.AIResultOut(
            available=True,
            model=ai.get("model"),
            suggested_type=schemas.IncidentTypeOut.model_validate(suggested) if suggested else None,
            confidence=report.ai_confidence,
            zone_risk=report.ai_zone_risk,
            matches_user_choice=(suggested.id == incident_type.id) if suggested else None,
            top_predictions=ai.get("top_predictions", []),
        )
    db.commit()
    db.refresh(report)

    # 4) Meter el reporte a la COLA DE PRIORIDAD de moderacion
    position = engine.add_report(ReportItem.from_model(report), first)
    return schemas.ReportCreatedOut(
        report=report_out(report, 0), ai=ai_out, queue_position=position, queue_size=len(engine.moderation_queue)
    )


@router.get("/reports", response_model=List[schemas.ReportOut])
def list_reports(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    neighborhood_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    """Historial por rango de fechas usando el ARBOL BINARIO DE BUSQUEDA."""
    end = date_to or datetime.now(timezone.utc)
    start = date_from or (end - timedelta(days=30))
    ids = engine.range_ids(start, end)
    ids.reverse()  # mas recientes primero
    if neighborhood_id is not None or status_filter is not None:
        filtered = []
        for rid in ids:
            item = engine.get_item(rid)
            if item is None:
                continue
            if neighborhood_id is not None and item.neighborhood_id != neighborhood_id:
                continue
            if status_filter is not None and item.status != status_filter:
                continue
            filtered.append(rid)
        ids = filtered
    return reports_in_order(db, ids[:limit])


@router.get("/reports/map", response_model=List[schemas.ReportOut])
def map_reports(db: Session = Depends(get_db)):
    """Alertas activas (publicadas o verificadas) para pintar en el mapa."""
    return reports_in_order(db, engine.feed_ids(None, limit=500))


@router.get("/reports/mine", response_model=List[schemas.ReportOut])
def my_reports(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.scalars(
        select(models.Report).where(models.Report.user_id == user.id).order_by(models.Report.created_at.desc())
    ).unique().all()
    conf = confirmations_for(db, [r.id for r in rows])
    return [report_out(r, conf.get(r.id, 0)) for r in rows]


@router.get("/feed", response_model=List[schemas.ReportOut])
def feed(neighborhood_id: Optional[int] = None, limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    """Feed de alertas activas. Por barrio = LISTA ENLAZADA; general = merge sort por prioridad."""
    return reports_in_order(db, engine.feed_ids(neighborhood_id, limit))


@router.get("/reports/{report_id}", response_model=schemas.ReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = get_report_or_404(db, report_id)
    return report_out(report, confirmations_for(db, [report_id]).get(report_id, 0))


@router.get("/reports/{report_id}/history", response_model=List[schemas.StatusEntryOut])
def report_history(report_id: int, db: Session = Depends(get_db)):
    """La PILA de estados del reporte, del tope a la base."""
    get_report_or_404(db, report_id)
    return [schemas.StatusEntryOut(**e.to_dict()) for e in engine.status_stack(report_id)]


@router.post("/reports/{report_id}/verify", response_model=schemas.ReportOut)
def verify_report(
    report_id: int,
    data: schemas.VerifyIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Un vecino confirma que la alerta es real. Con N confirmaciones pasa a 'verified'."""
    report = get_report_or_404(db, report_id)
    if report.status not in ("published", "verified"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se pueden confirmar alertas publicadas")
    if report.user_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No puedes confirmar tu propio reporte")
    db.add(models.ReportVerification(report_id=report.id, user_id=user.id, is_confirmed=data.is_confirmed, comment=data.comment))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya confirmaste este reporte")
    count = confirmations_for(db, [report.id]).get(report.id, 0)
    if report.status == "published" and count >= get_settings().verifications_required:
        change_status(db, report, "verified", user, f"Verificado por {count} vecinos")
    return report_out(report, count)
