"""
Cliente HTTP hacia el COMPONENTE DE IA (servicio aparte, como recomendo el profe).

El backend NO sabe que modelo se esta usando: solo llama a la API del
componente de IA. Si se cambia el modelo alla (variable de entorno), aca no
se toca nada.

Si el servicio de IA no responde (por ejemplo esta "dormido"), devolvemos
None y el backend sigue funcionando sin la parte de IA en vez de caerse.
"""

import logging
import time
from typing import Any, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings

log = logging.getLogger("alertabarrio.ai")


def _post(path: str, payload: dict) -> Tuple[Optional[dict], int]:
    settings = get_settings()
    url = settings.ai_service_url.rstrip("/") + path
    start = time.perf_counter()
    try:
        response = httpx.post(url, json=payload, timeout=settings.ai_timeout_seconds)
        response.raise_for_status()
        return response.json(), int((time.perf_counter() - start) * 1000)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Componente de IA no disponible en %s: %s", url, exc)
        return None, int((time.perf_counter() - start) * 1000)


def _log(db: Session, kind: str, result: Optional[dict], latency: int, **extra: Any) -> None:
    db.add(
        models.AIAnalysis(
            analysis_type=kind,
            model_name=(result or {}).get("model", "unavailable"),
            latency_ms=latency,
            result=result,
            **extra,
        )
    )


def analyze_report(db: Session, payload: dict, report_id: int, neighborhood_id: int) -> Optional[dict]:
    result, latency = _post("/api/v1/analyze-report", payload)
    _log(db, "report", result, latency, report_id=report_id, neighborhood_id=neighborhood_id)
    return result


def heatmap(db: Session, payload: dict, neighborhood_id: Optional[int]) -> Optional[dict]:
    result, latency = _post("/api/v1/heatmap", payload)
    # Guardamos un resumen en la bitacora (sin la grilla completa, que es grande)
    logged = None if result is None else {k: v for k, v in result.items() if k != "cells"}
    _log(db, "heatmap", logged, latency, neighborhood_id=neighborhood_id)
    return result


def summary(db: Session, payload: dict, neighborhood_id: int) -> Optional[dict]:
    result, latency = _post("/api/v1/summary", payload)
    _log(db, "summary", result, latency, neighborhood_id=neighborhood_id)
    return result


def status() -> dict:
    settings = get_settings()
    try:
        r = httpx.get(settings.ai_service_url.rstrip("/") + "/api/v1/models", timeout=5)
        r.raise_for_status()
        return {"available": True, **r.json()}
    except (httpx.HTTPError, ValueError) as exc:
        return {"available": False, "error": str(exc)}
