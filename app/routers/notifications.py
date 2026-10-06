from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user, require_moderator
from ..services import report_service
from ..services.engine import engine

router = APIRouter(prefix="/api/v1", tags=["subscriptions & notifications"])


# ----------------------------------------------------------- suscripciones
@router.get("/subscriptions/me", response_model=List[schemas.SubscriptionOut])
def my_subscriptions(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.scalars(select(models.Subscription).where(models.Subscription.user_id == user.id)).all()
    return [
        schemas.SubscriptionOut(neighborhood=schemas.NeighborhoodOut.model_validate(s.neighborhood), created_at=s.created_at)
        for s in rows
    ]


@router.post("/subscriptions/{neighborhood_id}", status_code=201)
def subscribe(neighborhood_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if db.get(models.Neighborhood, neighborhood_id) is None:
        raise HTTPException(404, "Barrio no encontrado")
    db.add(models.Subscription(user_id=user.id, neighborhood_id=neighborhood_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya estas suscrito a ese barrio")
    engine.subscribe(neighborhood_id, user.id)
    return {"subscribed": True, "subscribers_in_zone": engine.subscriber_count(neighborhood_id)}


@router.delete("/subscriptions/{neighborhood_id}")
def unsubscribe(neighborhood_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.scalar(
        select(models.Subscription).where(
            models.Subscription.user_id == user.id, models.Subscription.neighborhood_id == neighborhood_id
        )
    )
    if row is None:
        raise HTTPException(404, "No estabas suscrito a ese barrio")
    db.delete(row)
    db.commit()
    engine.unsubscribe(neighborhood_id, user.id)
    return {"subscribed": False}


# --------------------------------------------------------- notificaciones
@router.get("/notifications/me", response_model=List[schemas.NotificationOut])
def my_notifications(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.scalars(
        select(models.Notification)
        .where(models.Notification.user_id == user.id)
        .order_by(models.Notification.created_at.desc(), models.Notification.id.desc())
        .limit(100)
    ).all()


@router.post("/notifications/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_read(notification_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    n = db.get(models.Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(404, "Notificacion no encontrada")
    n.is_read = True
    db.commit()
    return n


@router.post("/notifications/dispatch")
def dispatch(db: Session = Depends(get_db), _: models.User = Depends(require_moderator)):
    """Despacha manualmente la COLA de notificaciones pendientes."""
    pending_before = len(engine.notification_queue)
    sent = report_service.dispatch_notifications(db)
    return {"pending_before": pending_before, "dispatched": sent}
