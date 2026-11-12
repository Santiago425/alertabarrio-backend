"""Ubicacion: a que barrio pertenece un punto del mapa."""

from math import asin, cos, radians, sin, sqrt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..barrios_pasto import COMUNAS


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos puntos (formula de haversine)."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(a))


def comuna_of(latitude: float, longitude: float) -> Optional[int]:
    """Comuna de Pasto que contiene el punto (punto en poligono, ray casting)."""
    for comuna, ring in COMUNAS.items():
        inside = False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > latitude) != (y2 > latitude) and longitude < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1:
                inside = not inside
        if inside:
            return comuna
    return None


def nearest_neighborhood(db: Session, latitude: float, longitude: float) -> Optional[models.Neighborhood]:
    """Barrio cuyo centro esta mas cerca del punto, buscando primero dentro de su comuna."""
    hoods = db.scalars(select(models.Neighborhood)).all()
    comuna = comuna_of(latitude, longitude)
    same = [n for n in hoods if comuna is not None and n.comuna == comuna]
    hoods = same or hoods
    return min(hoods, key=lambda n: distance_m(latitude, longitude, n.latitude, n.longitude), default=None)
