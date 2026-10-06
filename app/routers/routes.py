"""Ruta mas segura entre dos barrios usando el GRAFO + Dijkstra."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.engine import engine

router = APIRouter(prefix="/api/v1/routes", tags=["routes"])


@router.get("/safe", response_model=schemas.RouteOut)
def safe_route(from_id: int, to_id: int, db: Session = Depends(get_db)):
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
