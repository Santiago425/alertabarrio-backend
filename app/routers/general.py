from datetime import datetime, timezone

from fastapi import APIRouter

from ..config import get_settings
from ..services.engine import engine

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
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
def health():
    return {"status": "ok", "structures_loaded": engine.loaded}


@router.get("/api/v1/ds/state")
def data_structures_state():
    """Muestra el estado interno de TODAS las estructuras de datos."""
    return engine.snapshot()
