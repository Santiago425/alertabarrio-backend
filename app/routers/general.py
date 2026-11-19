from collections import Counter
from datetime import datetime, timedelta, timezone

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..database import get_db
from ..services.engine import ensure_aware, engine
from ..services.report_service import to_local
from ..security import require_moderator

router = APIRouter(tags=["general"])


@router.get("/api/v1/hello")
def hello():
    """Endpoint que pidio el profe para verificar que el backend esta desplegado."""
    settings = get_settings()
    return {
        "message": f"Hola mundo desde {settings.app_name}",
        "project": settings.project_name,
        "course": "Estructuras de Datos",
        "team": settings.team,
        "city": settings.city,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
def health():
    return {"status": "ok", "structures_loaded": engine.loaded}


@router.get("/api/v1/ds/state", dependencies=[Depends(require_moderator)])
def data_structures_state():
    """Muestra el estado interno de TODAS las estructuras de datos (solo admin/moderador: incluye pendientes)."""
    return engine.snapshot()


@router.get("/api/v1/stats")
def dashboard_stats(days: int = 14, db: Session = Depends(get_db)):
    """Numeros para el dashboard: totales por estado, por tipo y por dia."""
    days = max(7, min(days, 90))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    reports = db.scalars(select(models.Report)).unique().all()

    by_status = Counter(r.status for r in reports)
    recent = [r for r in reports if ensure_aware(r.occurred_at) >= since]
    by_type = Counter(r.incident_type.code for r in recent if r.status != "rejected")
    types = {t.code: t for t in db.scalars(select(models.IncidentType))}

    today = to_local(now).date()
    per_day = Counter(to_local(r.occurred_at).date() for r in recent if r.status != "rejected")
    timeline = [
        {"date": (today - timedelta(days=i)).isoformat(), "count": per_day.get(today - timedelta(days=i), 0)}
        for i in range(days - 1, -1, -1)
    ]
    this_week = sum(d["count"] for d in timeline[-7:])
    last_week = sum(d["count"] for d in timeline[-14:-7]) if days >= 14 else 0
    active_now = sum(engine.active_count_by_zone().values())

    return {
        "city": get_settings().city,
        "total_reports": len(reports),
        "by_status": {s: by_status.get(s, 0) for s in ("created", "in_review", "published", "verified", "rejected")},
        # activas = publicadas que todavia no vencen; las vencidas quedan en el historial
        "active_alerts": active_now,
        "expired_alerts": max(0, by_status.get("published", 0) + by_status.get("verified", 0) - active_now),
        "pending_moderation": len(engine.moderation_queue),
        "neighborhoods": db.query(models.Neighborhood).count(),
        "users": db.query(models.User).count(),
        "this_week": this_week,
        "last_week": last_week,
        "timeline": timeline,
        "by_type": [
            {"code": code, "name": types[code].name, "color": types[code].color, "count": n}
            for code, n in by_type.most_common()
            if code in types
        ],
    }


MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


@router.get("/api/v1/stats/zones")
def zone_stats(
    months: int = Query(6, ge=1, le=24),
    neighborhood_id: Optional[int] = None,
    comuna: Optional[int] = None,
    incident_type_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Estadisticas con TODOS los reportes guardados (tambien los que ya vencieron):
    cuantos incidentes hubo por mes, por barrio, por comuna, por hora y por dia.
    Ej: cuantos accidentes hubo en el Centro cada mes.
    """
    now_local = to_local(datetime.now(timezone.utc))
    # primer dia del mes de hace (months-1) meses
    y, m = now_local.year, now_local.month - (months - 1)
    while m <= 0:
        m += 12
        y -= 1
    month_keys = []
    yy, mm = y, m
    for _ in range(months):
        month_keys.append((yy, mm))
        mm += 1
        if mm > 12:
            mm, yy = 1, yy + 1

    reports = db.scalars(select(models.Report).where(models.Report.status != "rejected")).unique().all()
    rows = []
    for r in reports:
        local = to_local(r.occurred_at)
        if (local.year, local.month) < (y, m):
            continue
        if neighborhood_id is not None and r.neighborhood_id != neighborhood_id:
            continue
        if comuna is not None and r.neighborhood.comuna != comuna:
            continue
        if incident_type_id is not None and r.incident_type_id != incident_type_id:
            continue
        rows.append((r, local))

    types = {t.id: t for t in db.scalars(select(models.IncidentType))}
    by_month = {k: Counter() for k in month_keys}
    by_type, by_hood, by_comuna = Counter(), Counter(), Counter()
    by_hour, by_weekday = [0] * 24, [0] * 7
    hoods = {}
    for r, local in rows:
        key = (local.year, local.month)
        if key in by_month:
            by_month[key][r.incident_type_id] += 1
        by_type[r.incident_type_id] += 1
        by_hood[r.neighborhood_id] += 1
        hoods[r.neighborhood_id] = r.neighborhood
        if r.neighborhood.comuna:
            by_comuna[r.neighborhood.comuna] += 1
        by_hour[local.hour] += 1
        by_weekday[local.weekday()] += 1

    active_ids = set(engine.feed_ids(None, limit=100000))
    return {
        "months": months,
        "total": len(rows),
        "active_now": sum(1 for r, _ in rows if r.id in active_ids),
        "expired": sum(1 for r, _ in rows if r.status in ("published", "verified") and r.id not in active_ids),
        "by_month": [
            {
                "month": f"{yy}-{mm:02d}",
                "label": f"{MONTHS_ES[mm - 1]} {str(yy)[2:]}",
                "total": sum(c.values()),
                "by_type": {types[tid].code: n for tid, n in c.items() if tid in types},
            }
            for (yy, mm), c in by_month.items()
        ],
        "by_type": [
            {"id": tid, "code": types[tid].code, "name": types[tid].name, "color": types[tid].color, "count": n}
            for tid, n in by_type.most_common()
            if tid in types
        ],
        "top_neighborhoods": [
            {"id": nid, "name": hoods[nid].name, "comuna": hoods[nid].comuna, "count": n}
            for nid, n in by_hood.most_common(12)
        ],
        "by_comuna": [{"comuna": k, "count": by_comuna[k]} for k in sorted(by_comuna)],
        "by_hour": by_hour,
        "by_weekday": by_weekday,
    }
