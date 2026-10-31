from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.engine import engine
from ..services.geo import nearest_neighborhood

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/neighborhoods", response_model=List[schemas.NeighborhoodOut])
def list_neighborhoods(db: Session = Depends(get_db)):
    return db.scalars(select(models.Neighborhood).order_by(models.Neighborhood.name)).all()


@router.get("/neighborhoods/search", response_model=schemas.NeighborhoodOut)
def search_neighborhood(name: str, db: Session = Depends(get_db)):
    """Busqueda BINARIA sobre el catalogo de barrios ordenado por nombre."""
    nid = engine.find_neighborhood(name)
    if nid is None:
        raise HTTPException(404, f"No encontramos el barrio '{name}'")
    return db.get(models.Neighborhood, nid)


@router.get("/neighborhoods/nearest", response_model=schemas.NeighborhoodOut)
def nearest(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180), db: Session = Depends(get_db)):
    """Barrio al que pertenece un punto del mapa (el de centro mas cercano)."""
    hood = nearest_neighborhood(db, lat, lng)
    if hood is None:
        raise HTTPException(404, "No hay barrios registrados")
    return hood


@router.get("/neighborhoods/ranking")
def neighborhood_ranking(db: Session = Depends(get_db)):
    """Barrios con mas gravedad acumulada en alertas activas (ordenado con quick sort)."""
    names = {n.id: n.name for n in db.scalars(select(models.Neighborhood)).all()}
    counts = engine.active_count_by_zone()
    return [
        {
            "neighborhood_id": nid,
            "neighborhood": names.get(nid, str(nid)),
            "active_alerts": counts.get(nid, 0),
            "active_severity": sev,
            "subscribers": engine.subscriber_count(nid),
        }
        for nid, sev in engine.ranking()
    ]


@router.get("/neighborhoods/connections", response_model=List[schemas.ConnectionOut])
def list_connections(db: Session = Depends(get_db)):
    rows = db.scalars(select(models.NeighborhoodConnection)).all()
    return [
        schemas.ConnectionOut(
            from_id=c.from_neighborhood_id,
            to_id=c.to_neighborhood_id,
            distance_meters=c.distance_meters,
            road_name=c.road_name,
        )
        for c in rows
    ]


@router.get("/incident-types", response_model=List[schemas.IncidentTypeOut])
def list_incident_types(db: Session = Depends(get_db)):
    return db.scalars(select(models.IncidentType).order_by(models.IncidentType.severity_level.desc())).all()
