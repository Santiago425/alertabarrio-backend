"""Configuracion leida de variables de entorno (archivo .env en local)."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AlertaBarrio API"
    project_name: str = "AlertaBarrio"
    # Nombres de los integrantes separados por coma (se muestran en /api/v1/hello)
    team_members: str = "Integrante 1,Integrante 2"

    database_url: str = "postgresql+psycopg2://alerta:alerta@localhost:5432/alertabarrio"
    seed_on_startup: bool = True
    # Cuenta de revision para el profesor (solo se crea si hay clave)
    profesor_email: str = "profesor@alertabarrio.co"
    profesor_password: str = ""
    # Clave de las cuentas de prueba que crea el seed (admin@, moderador@, ana@...)
    demo_password: str = "Alerta2026*"

    jwt_secret: str = "cambiar-este-secreto-en-produccion"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    # Costo de bcrypt (2^rounds iteraciones). 12 tarda ~0.25 s por intento.
    bcrypt_rounds: int = 12
    # Intentos fallidos de login permitidos antes de bloquear el correo
    login_max_attempts: int = 5
    login_lock_minutes: int = 10
    # Solicitudes de login/registro permitidas por IP en la ventana
    auth_rate_limit: int = 20
    auth_rate_window_seconds: int = 300

    # Ciudad que muestra la app
    city: str = "Pasto"

    # URL del componente de IA (servicio separado)
    ai_service_url: str = "http://localhost:8001"
    ai_timeout_seconds: float = 20.0
    # Render (plan gratis) duerme la IA; el chat espera hasta este tiempo a que despierte
    ai_wake_seconds: float = 45.0

    # Origenes permitidos para el frontend (CORS), separados por coma
    cors_origins: str = "*"

    # Zona horaria para analizar patrones (dia de la semana / hora)
    timezone: str = "America/Bogota"

    # Cuantas confirmaciones de vecinos se necesitan para "verificar" un reporte
    verifications_required: int = 2

    @property
    def team(self) -> List[str]:
        return [m.strip() for m in self.team_members.split(",") if m.strip()]

    @property
    def cors_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
