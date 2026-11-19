"""Ruta mas segura entre dos barrios usando el GRAFO + Dijkstra, e historial de rutas del usuario."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user, get_optional_user
from ..services.engine import engine, ensure_aware

router = APIRouter(prefix="/api/v1/routes", tags=["routes"])


@router.get("/safe", response_model=schemas.RouteOut)
def safe_route(
    from_id: int,
    to_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_optional_user),
):
    route = compute_safe_route(db, from_id, to_id)
    if user is not None:
        remember_route(db, user, from_id, to_id)
    return route


def remember_route(db: Session, user: models.User, from_id: int, to_id: int) -> None:
    """Guarda la ruta en el historial del usuario (si ya estaba, sube el contador)."""
    row = db.scalar(
        select(models.SavedRoute).where(
            models.SavedRoute.user_id == user.id,
            models.SavedRoute.from_neighborhood_id == from_id,
            models.SavedRoute.to_neighborhood_id == to_id,
        )
    )
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(models.SavedRoute(user_id=user.id, from_neighborhood_id=from_id, to_neighborhood_id=to_id, last_used_at=now))
    else:
        row.times_used += 1
        row.last_used_at = now
    db.commit()


def _saved_out(r: models.SavedRoute) -> schemas.SavedRouteOut:
    return schemas.SavedRouteOut(
        id=r.id,
        from_neighborhood=schemas.NeighborhoodOut.model_validate(r.from_neighborhood),
        to_neighborhood=schemas.NeighborhoodOut.model_validate(r.to_neighborhood),
        label=r.label,
        times_used=r.times_used,
        created_at=ensure_aware(r.created_at),
        last_used_at=ensure_aware(r.last_used_at),
    )


def _own_route(db: Session, user: models.User, route_id: int) -> models.SavedRoute:
    row = db.get(models.SavedRoute, route_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Ruta no encontrada")
    return row


@router.get("/history", response_model=List[schemas.SavedRouteOut])
def route_history(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Mis rutas: las que tienen nombre primero, luego las mas recientes."""
    rows = db.scalars(select(models.SavedRoute).where(models.SavedRoute.user_id == user.id)).unique().all()
    rows = sorted(rows, key=lambda r: (r.label is None, -ensure_aware(r.last_used_at).timestamp()))
    return [_saved_out(r) for r in rows[:30]]


@router.patch("/history/{route_id}", response_model=schemas.SavedRouteOut)
def rename_route(
    route_id: int, data: schemas.SavedRouteLabelIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    """Ponerle nombre a una ruta, ej. 'De la U a mi casa'."""
    row = _own_route(db, user, route_id)
    row.label = (data.label or "").strip() or None
    db.commit()
    db.refresh(row)
    return _saved_out(row)


@router.delete("/history/{route_id}")
def delete_route(route_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db.delete(_own_route(db, user, route_id))
    db.commit()
    return {"deleted": True}


def compute_safe_route(db: Session, from_id: int, to_id: int) -> schemas.RouteOut:
    """Ruta segura (Dijkstra con castigo por alertas), la mas corta y la de menos saltos (BFS)."""
    neighborhoods = {n.id: n for n in db.scalars(select(models.Neighborhood)).all()}
    if from_id not in neighborhoods or to_id not in neighborhoods:
        raise HTTPException(404, "Barrio de origen o destino no existe")

    severity = engine.active_severity_by_zone()
    max_sev = max(severity.values(), default=0) or 1

    # Castigo de cada barrio: entre 0 y 3 segun la gravedad de sus alertas activas.
    def penalty(nid: int) -> float:
        return 3.0 * severity.get(nid, 0) / max_sev

    graph = engine.city_graph
    with engine.lock:
        safe_path, _ = graph.dijkstra(from_id, to_id, penalty)
        shortest_path, shortest_cost = graph.dijkstra(from_id, to_id)
        hops_path = graph.bfs_path(from_id, to_id)
    if safe_path is None:
        raise HTTPException(404, "No hay conexion entre esos barrios")

    def to_out(path):
        return [schemas.NeighborhoodOut.model_validate(neighborhoods[n]) for n in path]

    avoided = [
        {"neighborhood": neighborhoods[n].name, "active_severity": severity.get(n, 0)}
        for n in shortest_path
        if n not in safe_path
    ]
    safe_m = graph.path_length(safe_path)
    if avoided:
        explanation = (
            f"La ruta segura evita {', '.join(a['neighborhood'] for a in avoided)} por alertas activas; "
            f"recorre {safe_m / 1000:.1f} km en vez de {shortest_cost / 1000:.1f} km."
        )
    else:
        risky = [neighborhoods[n].name for n in safe_path if severity.get(n, 0) > 0]
        if risky:
            explanation = (
                "No hay un desvio razonable: la ruta mas corta tambien es la de menor riesgo, "
                f"pero pasa por {', '.join(risky)} con alertas activas. Tenga precaucion."
            )
        else:
            explanation = "La ruta mas corta ya es segura: no pasa por barrios con alertas activas."

    return schemas.RouteOut(
        from_neighborhood=to_out([from_id])[0],
        to_neighborhood=to_out([to_id])[0],
        safe_path=to_out(safe_path),
        safe_path_meters=round(safe_m, 1),
        shortest_path=to_out(shortest_path),
        shortest_path_meters=round(shortest_cost, 1),
        fewest_hops_path=to_out(hops_path or []),
        avoided=avoided,
        explanation=explanation,
    )
