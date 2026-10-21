"""
Cliente HTTP hacia el COMPONENTE DE IA (servicio aparte, como recomendo el profe).

El backend NO sabe que modelo se esta usando: solo llama a la API del
componente de IA. Si se cambia el modelo alla (variable de entorno), aca no
se toca nada.

Si el servicio de IA no responde (por ejemplo esta "dormido"), devolvemos
None y el backend sigue funcionando sin la parte de IA en vez de caerse.
"""

import logging
import threading
import time
from typing import Any, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings

log = logging.getLogger("alertabarrio.ai")


# Errores que Render devuelve mientras el servicio de IA esta dormido o arrancando
WAKING_CODES = {502, 503, 504}
_last_wake = 0.0


def _wake_up() -> None:
    """Despierta la IA en segundo plano (sin bloquear la respuesta al usuario)."""
    global _last_wake
    if time.monotonic() - _last_wake < 60:
        return
    _last_wake = time.monotonic()
    url = get_settings().ai_service_url.rstrip("/") + "/api/v1/models"

    def ping() -> None:
        try:
            httpx.get(url, timeout=90)
        except httpx.HTTPError:
            pass

    threading.Thread(target=ping, daemon=True).start()


def _post(path: str, payload: dict, wait_s: float = 0) -> Tuple[Optional[dict], int]:
    """POST al componente de IA. Con wait_s > 0 reintenta mientras la IA despierta."""
    settings = get_settings()
    url = settings.ai_service_url.rstrip("/") + path
    start = time.perf_counter()
    pause = 2.0
    while True:
        try:
            response = httpx.post(url, json=payload, timeout=settings.ai_timeout_seconds)
            response.raise_for_status()
            return response.json(), int((time.perf_counter() - start) * 1000)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in WAKING_CODES:
                log.warning("Componente de IA respondio con error en %s: %s", url, exc)
                return None, int((time.perf_counter() - start) * 1000)
            error: Exception = exc
        except (httpx.TransportError, ValueError) as exc:
            error = exc
        if time.perf_counter() - start + pause > wait_s:
            log.warning("Componente de IA no disponible en %s: %s", url, error)
            _wake_up()
            return None, int((time.perf_counter() - start) * 1000)
        time.sleep(pause)
        pause = min(pause * 1.5, 8.0)


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


def chat(db: Session, payload: dict, neighborhood_id: Optional[int]) -> Optional[dict]:
    result, latency = _post("/api/v1/chat", payload, wait_s=get_settings().ai_wake_seconds)
    _log(db, "chat", None if result is None else {"model": result.get("model")}, latency, neighborhood_id=neighborhood_id)
    return result


def status() -> dict:
    settings = get_settings()
    try:
        r = httpx.get(settings.ai_service_url.rstrip("/") + "/api/v1/models", timeout=5)
        r.raise_for_status()
        data = r.json()
        # el componente de IA llama "available" a la lista de modelos que tiene;
        # aca "available" significa "la IA responde", y la lista va en "options"
        return {**data, "options": data.get("available"), "available": True}
    except (httpx.HTTPError, ValueError) as exc:
        _wake_up()
        return {"available": False, "error": str(exc)}
