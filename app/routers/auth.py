from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..serializers import user_out
from ..services.engine import engine

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenOut, status_code=201)
def register(data: schemas.RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo")
    if data.neighborhood_id is not None and db.get(models.Neighborhood, data.neighborhood_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El barrio no existe")
    citizen = db.scalar(select(models.Role).where(models.Role.name == "citizen"))
    user = models.User(
        full_name=data.full_name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        phone=data.phone,
        role_id=citizen.id,
        neighborhood_id=data.neighborhood_id,
    )
    db.add(user)
    db.flush()
    # Si eligio barrio, lo suscribimos automaticamente a las alertas de su barrio
    if data.neighborhood_id is not None:
        db.add(models.Subscription(user_id=user.id, neighborhood_id=data.neighborhood_id))
    db.commit()
    db.refresh(user)
    if data.neighborhood_id is not None:
        engine.subscribe(data.neighborhood_id, user.id)
    return schemas.TokenOut(access_token=create_access_token(user), user=user_out(user))


@router.post("/login", response_model=schemas.TokenOut)
def login(data: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contrasena incorrectos")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La cuenta esta desactivada")
    return schemas.TokenOut(access_token=create_access_token(user), user=user_out(user))


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user_out(user)
