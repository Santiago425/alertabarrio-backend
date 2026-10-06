"""
Endpoints que usan el componente de IA:
    - Mapa de calor predictivo (patrones por zona, dia y hora)
    - Resumen diario en lenguaje natural de un barrio
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..database import get_db
from ..services import ai_client
from ..services.report_service import to_local

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/status")
def ai_status():
    """Que modelos tiene configurados el componente de IA."""
    return ai_client.status()


@router.get("/heatmap", response_model=schemas.HeatmapOut)
def heatmap(
    days: int = Query(120, ge=7, le=730),
    neighborhood_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = select(models.Report).where(models.Report.occurred_at >= since, models.Report.status != "rejected")
    if neighborhood_id is not None:
        q = q.where(models.Report.neighborhood_id == neighborhood_id)
    reports = db.scalars(q).unique().all()
    neighborhoods = db.scalars(select(models.Neighborhood)).all()
    names = {n.id: n.name for n in neighborhoods}

    payload = {
        "reports": [
            {
                "id": r.id,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "occurred_at": to_local(r.occurred_at).isoformat(),
                "severity": r.incident_type.severity_level,
                "incident_type_code": r.incident_type.code,
                "neighborhood_id": r.neighborhood_id,
            }
            for r in reports
        ],
        "neighborhoods": [
            {"id": n.id, "name": n.name, "latitude": n.latitude, "longitude": n.longitude} for n in neighborhoods
        ],
    }
    result = ai_client.heatmap(db, payload, neighborhood_id)

    if result is None:
        # Plan B si la IA no responde: pintamos los puntos crudos sin prediccion
        db.commit()
        return schemas.HeatmapOut(
            available=False,
            model="sin-ia (puntos crudos)",
            reports_analyzed=len(reports),
            cells=[
                schemas.HeatCellOut(latitude=r.latitude, longitude=r.longitude, intensity=r.incident_type.severity_level / 5)
                for r in reports
            ],
            hotspots=[],
            neighborhood_risk=[],
            insights=["El componente de IA no esta disponible en este momento."],
        )

    # Guardamos las zonas calientes en la tabla risk_hotspots
    hotspots = result.get("hotspots", [])
    affected = {h["neighborhood_id"] for h in hotspots}
    if affected:
        db.execute(delete(models.RiskHotspot).where(models.RiskHotspot.neighborhood_id.in_(affected)))
    for h in hotspots:
        db.add(
            models.RiskHotspot(
                neighborhood_id=h["neighborhood_id"],
                day_of_week=h["day_of_week"],
                hour_block=h["hour_block"],
                risk_score=h["risk_score"],
                model_name=result.get("model", "unknown"),
            )
        )
    db.commit()

    return schemas.HeatmapOut(
        available=True,
        model=result.get("model", "unknown"),
        reports_analyzed=len(reports),
        cells=[schemas.HeatCellOut(**c) for c in result.get("cells", [])],
        hotspots=[
            schemas.HotspotOut(neighborhood_name=names.get(h["neighborhood_id"], "?"), **h) for h in hotspots[:20]
        ],
        neighborhood_risk=[
            {**nr, "neighborhood_name": names.get(nr["neighborhood_id"], "?")} for nr in result.get("neighborhood_risk", [])
        ],
        insights=result.get("insights", []),
    )


@router.get("/daily-summary", response_model=schemas.SummaryOut)
def daily_summary(
    neighborhood_id: int,
    summary_date: Optional[date] = Query(None, alias="date"),
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    neighborhood = db.get(models.Neighborhood, neighborhood_id)
    if neighborhood is None:
        raise HTTPException(404, "Barrio no encontrado")
    tz = ZoneInfo(get_settings().timezone)
    day = summary_date or datetime.now(tz).date()

    cached = db.scalar(
        select(models.DailySummary).where(
            models.DailySummary.neighborhood_id == neighborhood_id, models.DailySummary.summary_date == day
        )
    )
    if cached is not None and not refresh:
        return schemas.SummaryOut(
            available=True,
            neighborhood=schemas.NeighborhoodOut.model_validate(neighborhood),
            summary_date=day,
            reports_count=cached.reports_count,
            summary_text=cached.summary_text,
            model=cached.model_name,
            cached=True,
        )

    day_start = datetime.combine(day, time.min, tzinfo=tz)
    week_start = day_start - timedelta(days=6)
    day_end = day_start + timedelta(days=1)
    rows = db.scalars(
        select(models.Report)
        .where(
            models.Report.neighborhood_id == neighborhood_id,
            models.Report.occurred_at >= week_start,
            models.Report.occurred_at < day_end,
            models.Report.status != "rejected",
        )
        .order_by(models.Report.occurred_at)
    ).unique().all()

    def as_dict(r: models.Report) -> dict:
        return {
            "title": r.title,
            "description": r.description,
            "incident_type": r.incident_type.name,
            "severity": r.incident_type.severity_level,
            "status": r.status,
            "occurred_at": to_local(r.occurred_at).isoformat(),
        }

    today = [as_dict(r) for r in rows if to_local(r.occurred_at).date() == day]
    week = [as_dict(r) for r in rows]
    hotspots = db.scalars(
        select(models.RiskHotspot)
        .where(models.RiskHotspot.neighborhood_id == neighborhood_id)
        .order_by(models.RiskHotspot.risk_score.desc())
        .limit(3)
    ).all()

    payload = {
        "neighborhood_name": neighborhood.name,
        "date": day.isoformat(),
        "reports": today,
        "week_reports": week,
        "hotspots": [{"day_of_week": h.day_of_week, "hour_block": h.hour_block, "risk_score": h.risk_score} for h in hotspots],
    }
    result = ai_client.summary(db, payload, neighborhood_id)
    if result is None:
        db.commit()
        return schemas.SummaryOut(
            available=False,
            neighborhood=schemas.NeighborhoodOut.model_validate(neighborhood),
            summary_date=day,
            reports_count=len(today),
            summary_text=f"Hoy hay {len(today)} reportes en {neighborhood.name}. (El componente de IA no respondio.)",
            model="sin-ia",
        )

    if cached is None:
        cached = models.DailySummary(neighborhood_id=neighborhood_id, summary_date=day)
        db.add(cached)
    cached.summary_text = result["summary"]
    cached.model_name = result.get("model", "unknown")
    cached.reports_count = len(today)
    db.commit()
    return schemas.SummaryOut(
        available=True,
        neighborhood=schemas.NeighborhoodOut.model_validate(neighborhood),
        summary_date=day,
        reports_count=len(today),
        summary_text=cached.summary_text,
        model=cached.model_name,
    )


@router.get("/hotspots", response_model=list[schemas.HotspotOut])
def stored_hotspots(neighborhood_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Zonas calientes guardadas en la BD por el ultimo analisis."""
    q = select(models.RiskHotspot, models.Neighborhood.name).join(
        models.Neighborhood, models.Neighborhood.id == models.RiskHotspot.neighborhood_id
    )
    if neighborhood_id is not None:
        q = q.where(models.RiskHotspot.neighborhood_id == neighborhood_id)
    rows = db.execute(q.order_by(models.RiskHotspot.risk_score.desc()).limit(50)).all()
    return [
        schemas.HotspotOut(
            neighborhood_id=h.neighborhood_id,
            neighborhood_name=name,
            day_of_week=h.day_of_week,
            hour_block=h.hour_block,
            risk_score=h.risk_score,
        )
        for h, name in rows
    ]
