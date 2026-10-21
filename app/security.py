"""
Seguridad del login: hash de contrasenas con bcrypt y tokens JWT.

Las contrasenas NUNCA se guardan en texto plano. bcrypt es una funcion de
hash lenta a proposito y con "sal" aleatoria por usuario:
    - la misma contrasena da un hash distinto en cada cuenta (la sal),
    - probar millones de contrasenas cuesta mucho tiempo (el costo, 2^12 rondas),
    - el hash no se puede "desencriptar": para entrar se vuelve a calcular y se compara.

Ademas:
    - se exige una contrasena fuerte (ver validate_password_strength),
    - tras varios intentos fallidos el correo queda bloqueado unos minutos,
    - si el costo configurado sube, el hash se actualiza solo al iniciar sesion,
    - cada IP tiene un limite de solicitudes de login/registro por minuto,
    - verificacion en dos pasos opcional con una app de autenticacion (TOTP),
    - se pueden cerrar todas las sesiones abiertas (token_version en el JWT).
"""

import base64
import hashlib
import hmac
import re
import secrets
import struct
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


# bcrypt solo usa los primeros 72 bytes; una tilde o una ñ ocupan 2 bytes.
MAX_PASSWORD_BYTES = 72


def password_problems(password: str) -> List[str]:
    """Lista de requisitos que la contrasena NO cumple (vacia = contrasena valida)."""
    problems = []
    if len(password) < 8:
        problems.append("tener al menos 8 caracteres")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        problems.append(f"tener maximo {MAX_PASSWORD_BYTES} bytes")
    if not re.search(r"[a-zñáéíóú]", password):
        problems.append("tener una letra minuscula")
    if not re.search(r"[A-ZÑÁÉÍÓÚ]", password):
        problems.append("tener una letra mayuscula")
    if not re.search(r"\d", password):
        problems.append("tener un numero")
    if not re.search(r"[^\w\s]|_", password):
        problems.append("tener un simbolo (por ejemplo * . ! #)")
    return problems


def validate_password_strength(password: str) -> str:
    problems = password_problems(password)
    if problems:
        raise ValueError("La contrasena debe " + ", ".join(problems))
    return password


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def needs_rehash(password_hash: str) -> bool:
    """True si el hash se hizo con menos rondas que las configuradas ahora."""
    try:
        return int(password_hash.split("$")[2]) < get_settings().bcrypt_rounds
    except (IndexError, ValueError):
        return True


_DUMMY_HASH: Optional[str] = None


def burn_password_check(password: str) -> None:
    """
    Hace un bcrypt "de mentira" cuando el correo no existe, para que la
    respuesta tarde lo mismo y no se pueda adivinar que correos estan registrados.
    """
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("cuenta-que-no-existe")
    verify_password(password, _DUMMY_HASH)


class LoginThrottle:
    """Bloquea un correo unos minutos despues de varios intentos fallidos seguidos."""

    def __init__(self) -> None:
        self._failures: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> List[float]:
        window = get_settings().login_lock_minutes * 60
        attempts = [t for t in self._failures.get(key, []) if now - t < window]
        self._failures[key] = attempts
        return attempts

    def seconds_locked(self, key: str) -> int:
        settings = get_settings()
        now = time.monotonic()
        with self._lock:
            attempts = self._recent(key, now)
            if len(attempts) < settings.login_max_attempts:
                return 0
            return max(1, int(attempts[0] + settings.login_lock_minutes * 60 - now))

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_throttle = LoginThrottle()


class RateLimiter:
    """Ventana deslizante por IP: frena bots que prueban muchos correos distintos."""

    def __init__(self) -> None:
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: int) -> int:
        """Registra un intento; devuelve los segundos a esperar (0 = permitido)."""
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < window_s]
            if len(hits) >= limit:
                self._hits[key] = hits
                return max(1, int(hits[0] + window_s - now))
            hits.append(now)
            self._hits[key] = hits
            return 0


auth_rate_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Render y Vercel ponen la IP real del cliente en X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


def limit_auth_requests(request: Request) -> None:
    settings = get_settings()
    wait = auth_rate_limiter.hit(client_ip(request), settings.auth_rate_limit, settings.auth_rate_window_seconds)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiadas solicitudes desde tu conexion. Espera un momento e intenta de nuevo",
            headers={"Retry-After": str(wait)},
        )


# ------------------------------------------------------------------ verificacion en dos pasos (TOTP)
# Mismo algoritmo que usan Google Authenticator, Microsoft Authenticator o Authy (RFC 6238):
# codigo de 6 digitos que cambia cada 30 segundos, calculado con HMAC-SHA1 de un secreto compartido.

TOTP_STEP = 30


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, at: Optional[float] = None) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((time.time() if at is None else at) // TOTP_STEP)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def verify_totp(secret: str, code: str) -> bool:
    """Acepta el codigo actual y el de 30 s antes o despues (por si el reloj del celular va desfasado)."""
    code = (code or "").replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    now = time.time()
    return any(hmac.compare_digest(totp_code(secret, now + d * TOTP_STEP), code) for d in (-1, 0, 1))


def totp_uri(secret: str, email: str) -> str:
    return f"otpauth://totp/AlertaBarrio:{email}?secret={secret}&issuer=AlertaBarrio&digits=6&period={TOTP_STEP}"


def create_access_token(user: User) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user.id),
        "role": user.role.name,
        "tv": user.token_version,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalido o vencido")


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Debes iniciar sesion")
    payload = _decode(credentials.credentials)
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado o inactivo")
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesion se cerro. Inicia sesion de nuevo")
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


def require_moderator(user: User = Depends(get_current_user)) -> User:
    if user.role.name not in ("moderator", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo moderadores pueden hacer esto")
    return user
