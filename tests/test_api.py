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
        json={"full_name": "Vecina Nueva", "email": "nueva@test.co", "password": "Secreta.123", "neighborhood_id": 1},
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "nueva@test.co" and me.json()["role"] == "citizen"
    # correo repetido
    assert client.post(
        "/api/v1/auth/register", json={"full_name": "Otra", "email": "nueva@test.co", "password": "Secreta.123"}
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
            "latitude": 1.2136,
            "longitude": -77.2811,
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
    assert client.get("/api/v1/neighborhoods/search", params={"name": "palermo"}).json()["name"] == "Palermo"


def test_ai_endpoints(client, ai_up):
    assert client.get("/api/v1/ai/heatmap").json()["available"] is True
    s = client.get("/api/v1/ai/daily-summary", params={"neighborhood_id": 1}).json()
    assert s["summary_text"].startswith("Resumen de Centro")
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


def test_weak_passwords_are_rejected(client):
    base = {"full_name": "Vecino Debil", "email": "debil@test.co"}
    for weak in ["Cort1*a", "sinmayuscula1*", "SINMINUSCULA1*", "SinNumero*", "SinSimbolo123", "A1*" + "ñ" * 40]:
        r = client.post("/api/v1/auth/register", json={**base, "password": weak[:72]})
        assert r.status_code == 422, weak
    assert client.post("/api/v1/auth/register", json={**base, "password": "Bien.Fuerte9"}).status_code == 201


def test_password_is_hashed_with_bcrypt(client):
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        u = db.query(models.User).filter_by(email="debil@test.co").one()
        assert u.password_hash.startswith("$2") and "Bien.Fuerte9" not in u.password_hash
    finally:
        db.close()


def test_change_password(client):
    r = client.post("/api/v1/auth/login", json={"email": "debil@test.co", "password": "Bien.Fuerte9"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    bad = client.post("/api/v1/auth/change-password", headers=h, json={"current_password": "otra", "new_password": "Nueva.Clave1"})
    assert bad.status_code == 400
    ok = client.post("/api/v1/auth/change-password", headers=h, json={"current_password": "Bien.Fuerte9", "new_password": "Nueva.Clave1"})
    assert ok.status_code == 204
    assert client.post("/api/v1/auth/login", json={"email": "debil@test.co", "password": "Nueva.Clave1"}).status_code == 200


def test_login_lockout_after_failed_attempts(client):
    from app.security import login_throttle

    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email": "jorge@alertabarrio.co", "password": "mala"}).status_code == 401
    # ni con la contrasena correcta entra mientras este bloqueado
    r = client.post("/api/v1/auth/login", json={"email": "jorge@alertabarrio.co", "password": "Alerta2026*"})
    assert r.status_code == 429 and "Retry-After" in r.headers
    login_throttle.reset("jorge@alertabarrio.co")
    assert client.post("/api/v1/auth/login", json={"email": "jorge@alertabarrio.co", "password": "Alerta2026*"}).status_code == 200


def test_city_is_pasto_and_stats(client):
    assert client.get("/api/v1/hello").json()["city"] == "Pasto"
    hoods = client.get("/api/v1/neighborhoods").json()
    assert {h["city"] for h in hoods} == {"Pasto"} and any(h["name"] == "Centro" for h in hoods)
    stats = client.get("/api/v1/stats").json()
    assert stats["total_reports"] > 100 and len(stats["timeline"]) == 14
    assert stats["active_alerts"] == stats["by_status"]["published"] + stats["by_status"]["verified"]


def test_migrate_existing_bogota_database_to_pasto(tmp_path):
    """La base que ya esta en Render tiene barrios de Bogota: se pasan a Pasto sin borrar datos."""
    from datetime import datetime, timezone

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app import models
    from app.database import Base
    from app.seed import migrate_to_pasto

    eng = create_engine(f"sqlite:///{tmp_path / 'bogota.db'}")
    Base.metadata.create_all(eng)
    with Session(eng) as db:
        role = models.Role(name="citizen", description="")
        chap = models.Neighborhood(name="Chapinero", city="Bogota", latitude=4.6486, longitude=-74.0628)
        kenn = models.Neighborhood(name="Kennedy", city="Bogota", latitude=4.628, longitude=-74.158)
        it = models.IncidentType(code="theft", name="Hurto", severity_level=3, color="#f59e0b")
        db.add_all([role, chap, kenn, it])
        db.flush()
        db.add(models.NeighborhoodConnection(from_neighborhood_id=chap.id, to_neighborhood_id=kenn.id, distance_meters=1, road_name="Calle 1"))
        user = models.User(full_name="Ana", email="a@a.co", password_hash="x", role_id=role.id, neighborhood_id=chap.id)
        db.add(user)
        db.flush()
        db.add(
            models.Report(
                user_id=user.id, neighborhood_id=chap.id, incident_type_id=it.id, title="Robo", description="Robo de celular",
                latitude=4.6486 + 0.002, longitude=-74.0628, occurred_at=datetime.now(timezone.utc), status="published", priority_score=60,
            )
        )
        db.add(models.Notification(user_id=user.id, message="Nueva alerta en Chapinero: Hurto"))
        db.commit()
        chap_id = chap.id

        assert migrate_to_pasto(db) is True
        assert migrate_to_pasto(db) is False  # la segunda vez no hace nada

        centro = db.get(models.Neighborhood, chap_id)
        assert (centro.name, centro.city) == ("Centro", "Pasto")
        report = db.scalars(select(models.Report)).one()
        assert report.neighborhood_id == chap_id and abs(report.latitude - (1.2136 + 0.0009)) < 1e-6
        assert db.scalars(select(models.User)).one().neighborhood_id == chap_id
        assert db.scalars(select(models.Notification)).one().message == "Nueva alerta en Centro: Hurto"
        roads = db.scalars(select(models.NeighborhoodConnection)).all()
        assert roads == []  # la via vieja de Bogota se borra; Centro y Lorenzo de Aldana no tienen via directa
