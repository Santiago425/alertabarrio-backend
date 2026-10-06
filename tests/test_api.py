"""Pruebas del ciclo completo de la API."""

from datetime import datetime, timedelta, timezone

from app.services.engine import engine

from .conftest import login


def test_hello(client):
    r = client.get("/api/v1/hello")
    assert r.status_code == 200
    body = r.json()
    assert body["project"] == "AlertaBarrio" and len(body["team"]) >= 1


def test_register_login_me(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Vecina Nueva", "email": "nueva@test.co", "password": "secreta123", "neighborhood_id": 1},
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "nueva@test.co" and me.json()["role"] == "citizen"
    # correo repetido
    assert client.post(
        "/api/v1/auth/register", json={"full_name": "Otra", "email": "nueva@test.co", "password": "secreta123"}
    ).status_code == 409
    # contrasena mala
    assert client.post("/api/v1/auth/login", json={"email": "nueva@test.co", "password": "malamala"}).status_code == 401


def test_requires_auth(client):
    assert client.post("/api/v1/reports", json={}).status_code == 401
    citizen = login(client, "ana@alertabarrio.co")
    assert client.get("/api/v1/moderation/queue", headers=citizen).status_code == 403


def _new_report(client, headers, title="Me robaron con pistola", type_id=5, hood=1):
    return client.post(
        "/api/v1/reports",
        headers=headers,
        json={
            "title": title,
            "description": "Un hombre con pistola me quito el celular frente a la tienda",
            "incident_type_id": type_id,
            "neighborhood_id": hood,
            "latitude": 4.65,
            "longitude": -74.06,
        },
    )


def test_full_cycle_with_priority_queue_and_stack(client, ai_up):
    ana = login(client, "ana@alertabarrio.co")
    mod = login(client, "moderador@alertabarrio.co")

    # 1) El vecino crea el reporte -> IA -> cola de prioridad
    r = _new_report(client, ana)
    assert r.status_code == 201, r.text
    data = r.json()
    rid = data["report"]["id"]
    assert data["ai"]["available"] and data["ai"]["suggested_type"]["code"] == "armed_robbery"
    # la IA detecto algo mas grave que "hurto" -> prioridad de robo armado (5*20 + 0.5*20)
    assert data["report"]["priority_score"] == 110.0
    assert data["queue_position"] == 1  # es el mas grave de la cola

    queue = client.get("/api/v1/moderation/queue", headers=mod).json()
    assert queue["reports"][0]["id"] == rid

    # 2) El moderador toma el siguiente (pop del heap) -> es este
    nxt = client.post("/api/v1/moderation/next", headers=mod).json()
    assert nxt["id"] == rid and nxt["status"] == "in_review"
    assert rid not in engine.moderation_queue

    # 3) Publicar -> entra al feed (lista enlazada) y se notifican los suscritos
    pub = client.post(f"/api/v1/moderation/reports/{rid}/publish", headers=mod, json={}).json()
    assert pub["report"]["status"] == "published" and pub["notifications_queued"] >= 1
    feed = client.get("/api/v1/feed", params={"neighborhood_id": 1}).json()
    assert feed[0]["id"] == rid
    carlos = login(client, "carlos@alertabarrio.co")
    notes = client.get("/api/v1/notifications/me", headers=carlos).json()
    assert any(n["report_id"] == rid for n in notes)

    # 4) Historial = pila (tope primero)
    hist = client.get(f"/api/v1/reports/{rid}/history").json()
    assert [h["new_status"] for h in hist] == ["published", "in_review", "created"]

    # 5) Deshacer publicacion -> sale del feed, vuelve a "en revision"
    undo = client.post(f"/api/v1/moderation/reports/{rid}/undo", headers=mod).json()
    assert undo["undone_status"] == "published" and undo["current_status"] == "in_review"
    assert rid not in [x["id"] for x in client.get("/api/v1/feed", params={"neighborhood_id": 1}).json()]

    # 6) Deshacer otra vez -> "created" y vuelve a la cola de prioridad
    undo = client.post(f"/api/v1/moderation/reports/{rid}/undo", headers=mod).json()
    assert undo["current_status"] == "created" and rid in engine.moderation_queue

    # 7) Ya no hay mas que deshacer
    assert client.post(f"/api/v1/moderation/reports/{rid}/undo", headers=mod).status_code == 409


def test_verification_by_neighbors(client, ai_up):
    ana = login(client, "ana@alertabarrio.co")
    mod = login(client, "moderador@alertabarrio.co")
    rid = _new_report(client, ana, title="Robo para verificar").json()["report"]["id"]
    client.post(f"/api/v1/moderation/reports/{rid}/publish", headers=mod, json={})
    assert client.post(f"/api/v1/reports/{rid}/verify", headers=ana, json={}).status_code == 409  # propio
    r1 = client.post(f"/api/v1/reports/{rid}/verify", headers=login(client, "carlos@alertabarrio.co"), json={})
    assert r1.json()["status"] == "published"
    r2 = client.post(f"/api/v1/reports/{rid}/verify", headers=login(client, "laura@alertabarrio.co"), json={})
    assert r2.json()["status"] == "verified" and r2.json()["confirmations"] == 2


def test_reject_invalid_transition(client, ai_up):
    ana = login(client, "ana@alertabarrio.co")
    mod = login(client, "moderador@alertabarrio.co")
    rid = _new_report(client, ana, title="Reporte falso").json()["report"]["id"]
    assert client.post(f"/api/v1/moderation/reports/{rid}/reject", headers=mod, json={}).json()["status"] == "rejected"
    assert client.post(f"/api/v1/moderation/reports/{rid}/publish", headers=mod, json={}).status_code == 409


def test_range_query_bst(client):
    now = datetime.now(timezone.utc)
    r = client.get("/api/v1/reports", params={"from": (now - timedelta(days=7)).isoformat(), "to": now.isoformat()})
    assert r.status_code == 200
    for rep in r.json():
        assert datetime.fromisoformat(rep["created_at"]) >= now - timedelta(days=7, seconds=1)


def test_safe_route_and_search(client):
    r = client.get("/api/v1/routes/safe", params={"from_id": 2, "to_id": 12})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["safe_path"][0]["id"] == 2 and body["safe_path"][-1]["id"] == 12
    assert client.get("/api/v1/neighborhoods/search", params={"name": "kennedy"}).json()["name"] == "Kennedy"


def test_ai_endpoints(client, ai_up):
    assert client.get("/api/v1/ai/heatmap").json()["available"] is True
    s = client.get("/api/v1/ai/daily-summary", params={"neighborhood_id": 1}).json()
    assert s["summary_text"].startswith("Resumen de Chapinero")
    assert client.get("/api/v1/ai/daily-summary", params={"neighborhood_id": 1}).json()["cached"] is True


def test_ai_down_does_not_break(client):
    # sin el mock la IA no responde: el backend sigue funcionando
    assert client.get("/api/v1/ai/heatmap").json()["available"] is False
    ana = login(client, "ana@alertabarrio.co")
    r = _new_report(client, ana, title="Sin IA")
    assert r.status_code == 201 and r.json()["ai"]["available"] is False


def test_ds_state(client):
    state = client.get("/api/v1/ds/state").json()
    for key in ("priority_queue", "status_stacks", "zone_feeds", "notification_queue", "timeline_bst", "city_graph"):
        assert key in state
    assert state["city_graph"]["connected"] is True
