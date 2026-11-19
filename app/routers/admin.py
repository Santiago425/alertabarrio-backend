"""
Panel del administrador: CONFIGURACION DE ALERTAS.

El profe pidio que los tipos de alerta no se cambien entrando a la base de
datos, sino desde un panel: crear tipos nuevos (ej. "Accidente de moto"),
cambiarles el nombre ("Atraco con arma blanca" -> "Atraco con armas"), la
gravedad, el color y CUANTO DURAN en el mapa antes de vencer.
"""

import re
import unicodedata
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import require_admin
from ..seed import CATALOG_CODES, CATEGORIES
from ..services.engine import engine

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _slug(name: str) -> str:
    """'Accidente de moto' -> 'accidente_de_moto' (codigo interno del tipo)."""
    plain = "".join(c for c in unicodedata.normalize("NFD", name.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", plain).strip("_")[:36] or "tipo"


def _admin_out(db: Session, t: models.IncidentType) -> schemas.IncidentTypeAdminOut:
    total = db.scalar(select(func.count()).select_from(models.Report).where(models.Report.incident_type_id == t.id)) or 0
    active = 0
    for rid in engine.feed_ids(None, limit=100000):
        item = engine.get_item(rid)
        if item is not None and item.incident_type_id == t.id:
            active += 1
    out = schemas.IncidentTypeAdminOut.model_validate(t)
    out.reports_total = total
    out.active_now = active
    return out


def _name_taken(db: Session, name: str, exclude_id: int = 0) -> bool:
    return (
        db.scalar(
            select(models.IncidentType.id).where(
                func.lower(models.IncidentType.name) == name.strip().lower(), models.IncidentType.id != exclude_id
            )
        )
        is not None
    )


@router.get("/incident-categories")
def list_categories(db: Session = Depends(get_db), _: models.User = Depends(require_admin)):
    """Categorias para agrupar los tipos (las del catalogo + las que haya creado el admin)."""
    used = {c for (c,) in db.execute(select(models.IncidentType.category)) if c}
    return CATEGORIES + sorted(used - set(CATEGORIES))


@router.get("/incident-types", response_model=List[schemas.IncidentTypeAdminOut])
def list_types(db: Session = Depends(get_db), _: models.User = Depends(require_admin)):
    rows = db.scalars(
        select(models.IncidentType).order_by(models.IncidentType.is_active.desc(), models.IncidentType.severity_level.desc())
    ).all()
    return [_admin_out(db, t) for t in rows]


@router.post("/incident-types", response_model=schemas.IncidentTypeAdminOut, status_code=201)
def create_type(data: schemas.IncidentTypeIn, db: Session = Depends(get_db), _: models.User = Depends(require_admin)):
    name = data.name.strip()
    if _name_taken(db, name):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un tipo llamado '{name}'")
    code, n = _slug(name), 2
    while db.scalar(select(models.IncidentType.id).where(models.IncidentType.code == code)) is not None:
        code = f"{_slug(name)}_{n}"
        n += 1
    t = models.IncidentType(
        code=code,
        name=name,
        severity_level=data.severity_level,
        color=data.color,
        duration_minutes=data.duration_minutes,
        is_active=data.is_active,
        category=data.category.strip(),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    engine.set_type_duration(t.id, t.duration_minutes or 0)
    return _admin_out(db, t)


@router.patch("/incident-types/{type_id}", response_model=schemas.IncidentTypeAdminOut)
def update_type(
    type_id: int, data: schemas.IncidentTypeUpdate, db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    t = db.get(models.IncidentType, type_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tipo de alerta no encontrado")
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
        if _name_taken(db, changes["name"], exclude_id=t.id):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un tipo llamado '{changes['name']}'")
    for key, value in changes.items():
        if value is not None:
            setattr(t, key, value)
    db.commit()
    db.refresh(t)
    # La nueva duracion aplica de una a las alertas que ya estan en el mapa
    engine.set_type_duration(t.id, t.duration_minutes or 0)
    return _admin_out(db, t)


@router.delete("/incident-types/{type_id}")
def delete_type(type_id: int, db: Session = Depends(get_db), _: models.User = Depends(require_admin)):
    """Si el tipo ya tiene reportes NO se borra (se perderian datos): se desactiva.
    Los tipos del catalogo base tampoco se borran (volverian a crearse al arrancar): se desactivan."""
    t = db.get(models.IncidentType, type_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tipo de alerta no encontrado")
    used = db.scalar(
        select(func.count())
        .select_from(models.Report)
        .where((models.Report.incident_type_id == t.id) | (models.Report.ai_suggested_type_id == t.id))
    )
    if used or t.code in CATALOG_CODES:
        t.is_active = False
        db.commit()
        reason = f"Tiene {used} reportes" if used else "Es del catalogo base"
        return {"deleted": False, "deactivated": True, "message": f"{reason}: se desactivo para no perder el historial."}
    db.delete(t)
    db.commit()
    return {"deleted": True, "deactivated": False, "message": "Tipo eliminado."}
