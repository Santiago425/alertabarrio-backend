"""Convierte objetos de la BD en los esquemas de salida."""

from typing import Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas
from .services.engine import ensure_aware


def user_out(user: models.User) -> schemas.UserOut:
    return schemas.UserOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role.name,
        neighborhood=schemas.NeighborhoodOut.model_validate(user.neighborhood) if user.neighborhood else None,
        created_at=ensure_aware(user.created_at),
    )


def confirmations_for(db: Session, report_ids: Iterable[int]) -> Dict[int, int]:
    ids = list(report_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(models.ReportVerification.report_id, func.count())
        .where(models.ReportVerification.report_id.in_(ids), models.ReportVerification.is_confirmed.is_(True))
        .group_by(models.ReportVerification.report_id)
    ).all()
    return {rid: count for rid, count in rows}


def report_out(r: models.Report, confirmations: Optional[int] = None) -> schemas.ReportOut:
    return schemas.ReportOut(
        id=r.id,
        title=r.title,
        description=r.description,
        latitude=r.latitude,
        longitude=r.longitude,
        occurred_at=ensure_aware(r.occurred_at),
        created_at=ensure_aware(r.created_at),
        status=r.status,
        priority_score=r.priority_score,
        neighborhood=schemas.NeighborhoodOut.model_validate(r.neighborhood),
        incident_type=schemas.IncidentTypeOut.model_validate(r.incident_type),
        reporter_name=r.user.full_name,
        photos=[p.url for p in r.photos],
        ai_suggested_type=schemas.IncidentTypeOut.model_validate(r.ai_suggested_type) if r.ai_suggested_type else None,
        ai_confidence=r.ai_confidence,
        ai_zone_risk=r.ai_zone_risk,
        confirmations=confirmations,
    )


def reports_in_order(db: Session, ids: List[int]) -> List[schemas.ReportOut]:
    """Trae los reportes de la BD respetando el orden que dio la estructura."""
    if not ids:
        return []
    rows = db.scalars(select(models.Report).where(models.Report.id.in_(ids))).unique().all()
    by_id = {r.id: r for r in rows}
    conf = confirmations_for(db, ids)
    return [report_out(by_id[i], conf.get(i, 0)) for i in ids if i in by_id]
