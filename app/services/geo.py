"""Ubicacion: a que barrio pertenece un punto del mapa."""

from math import asin, cos, radians, sin, sqrt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos puntos (formula de haversine)."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(a))


def nearest_neighborhood(db: Session, latitude: float, longitude: float) -> Optional[models.Neighborhood]:
    """Barrio cuyo centro esta mas cerca del punto."""
    hoods = db.scalars(select(models.Neighborhood)).all()
    return min(hoods, key=lambda n: distance_m(latitude, longitude, n.latitude, n.longitude), default=None)
