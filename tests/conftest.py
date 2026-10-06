import os
import tempfile

# Las pruebas usan PostgreSQL si viene DATABASE_URL (asi corre en GitHub Actions);
# si no, una base SQLite temporal.
if "DATABASE_URL" not in os.environ:
    _tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ.setdefault("AI_SERVICE_URL", "http://ai-no-disponible.invalid")
os.environ.setdefault("AI_TIMEOUT_SECONDS", "1")

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine as db_engine
from app.main import app
from app.services import ai_client

PASSWORD = "Alerta2026*"


def fake_ai_post(path: str, payload: dict):
    """Simula el componente de IA para no depender de la red en las pruebas."""
    if path.endswith("analyze-report"):
        text = payload["description"].lower()
        code = "armed_robbery" if "pistola" in text else payload["incident_type_code"]
        return {
            "model": "fake",
            "suggested_type_code": code,
            "confidence": 0.9,
            "zone_risk": 0.5,
            "top_predictions": [{"code": code, "probability": 0.9}],
        }, 5
    if path.endswith("heatmap"):
        return {"model": "fake", "cells": [], "hotspots": [], "neighborhood_risk": [], "insights": []}, 5
    if path.endswith("summary"):
        return {"model": "fake", "summary": f"Resumen de {payload['neighborhood_name']}"}, 5
    return None, 5


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(bind=db_engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ai_up(monkeypatch):
    monkeypatch.setattr(ai_client, "_post", fake_ai_post)


def login(client, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
