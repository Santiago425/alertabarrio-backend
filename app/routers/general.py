from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..database import get_db
from ..services.engine import ensure_aware, engine
from ..services.report_service import to_local

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


@router.get("/api/v1/ds/state")
def data_structures_state():
    """Muestra el estado interno de TODAS las estructuras de datos."""
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

    return {
        "city": get_settings().city,
        "total_reports": len(reports),
        "by_status": {s: by_status.get(s, 0) for s in ("created", "in_review", "published", "verified", "rejected")},
        "active_alerts": by_status.get("published", 0) + by_status.get("verified", 0),
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
