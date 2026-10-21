"""
Endpoints que usan el componente de IA:
    - Mapa de calor predictivo (patrones por zona, dia y hora)
    - Resumen diario en lenguaje natural de un barrio
"""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..database import get_db
from ..security import get_optional_user
from ..serializers import reports_in_order
from ..services.engine import engine, ensure_aware
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
        "city": neighborhood.city,
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


def _time_ago(dt: datetime) -> str:
    minutes = int((datetime.now(timezone.utc) - ensure_aware(dt)).total_seconds() // 60)
    if minutes < 60:
        return f"hace {max(minutes, 1)} min"
    if minutes < 60 * 24:
        return f"hace {minutes // 60} h"
    return f"hace {minutes // (60 * 24)} dias"


@router.post("/chat", response_model=schemas.ChatOut)
def chat(
    data: schemas.ChatIn,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_optional_user),
):
    """Asistente: el vecino pregunta y la IA responde con los datos reales de la ciudad."""
    hood_id = data.neighborhood_id or (user.neighborhood_id if user else None)
    hood = db.get(models.Neighborhood, hood_id) if hood_id else None
    names = {n.id: n.name for n in db.scalars(select(models.Neighborhood))}
    counts = engine.active_count_by_zone()
    ranking = [
        {"neighborhood": names.get(nid, str(nid)), "active_alerts": counts.get(nid, 0), "active_severity": sev}
        for nid, sev in engine.ranking()
    ]

    since = datetime.now(timezone.utc) - timedelta(days=90)
    slots: Counter = Counter()
    for r in db.scalars(select(models.Report).where(models.Report.occurred_at >= since, models.Report.status != "rejected")).unique():
        local = to_local(r.occurred_at)
        slots[(r.neighborhood_id, local.weekday(), min(3, local.hour // 6))] += r.incident_type.severity_level
    hotspots = [
        {"neighborhood": names.get(nid, str(nid)), "day_of_week": d, "hour_block": b}
        for (nid, d, b), _ in slots.most_common(5)
    ]

    recent = reports_in_order(db, engine.feed_ids(hood.id if hood else None, 8))
    payload = {
        "question": data.question.strip(),
        "context": {
            "city": get_settings().city,
            "neighborhood": hood.name if hood else None,
            "active_alerts": sum(counts.values()),
            "ranking": ranking[:8],
            "hotspots": hotspots,
            "recent": [
                {
                    "incident_type": r.incident_type.name,
                    "neighborhood": r.neighborhood.name,
                    "when": _time_ago(r.occurred_at),
                    "title": r.title,
                }
                for r in recent
            ],
        },
    }
    result = ai_client.chat(db, payload, hood.id if hood else None)
    db.commit()
    if result is None:
        return schemas.ChatOut(
            available=False,
            model="no disponible",
            answer="La IA no esta disponible en este momento. Intenta de nuevo en un minuto.",
        )
    return schemas.ChatOut(available=True, answer=result["answer"], model=result["model"])
