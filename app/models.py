"""
Modelo de base de datos (tablas y columnas en ingles, como pidio el profe).

14 tablas:
    roles, users, neighborhoods, neighborhood_connections, incident_types,
    reports, report_photos, report_status_history, report_verifications,
    subscriptions, notifications, ai_analyses, daily_summaries, risk_hotspots

El diagrama entidad-relacion esta en alertabarrio-database/er_diagram.png
"""

from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

REPORT_STATUSES = ("created", "in_review", "published", "verified", "rejected")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # citizen, moderator, admin
    description: Mapped[Optional[str]] = mapped_column(String(200))

    users: Mapped[List["User"]] = relationship(back_populates="role")


class Neighborhood(Base):
    __tablename__ = "neighborhoods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NeighborhoodConnection(Base):
    """Aristas del grafo de barrios (para la ruta segura)."""

    __tablename__ = "neighborhood_connections"
    __table_args__ = (
        UniqueConstraint("from_neighborhood_id", "to_neighborhood_id", name="uq_connection"),
        CheckConstraint("from_neighborhood_id <> to_neighborhood_id", name="ck_connection_not_self"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_neighborhood_id: Mapped[int] = mapped_column(ForeignKey("neighborhoods.id", ondelete="CASCADE"), nullable=False)
    to_neighborhood_id: Mapped[int] = mapped_column(ForeignKey("neighborhoods.id", ondelete="CASCADE"), nullable=False)
    distance_meters: Mapped[float] = mapped_column(Float, nullable=False)
    road_name: Mapped[Optional[str]] = mapped_column(String(120))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    neighborhood_id: Mapped[Optional[int]] = mapped_column(ForeignKey("neighborhoods.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    role: Mapped[Role] = relationship(back_populates="users", lazy="joined")
    neighborhood: Mapped[Optional[Neighborhood]] = relationship(lazy="joined")


class IncidentType(Base):
    __tablename__ = "incident_types"
    __table_args__ = (CheckConstraint("severity_level BETWEEN 1 AND 5", name="ck_severity_range"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    severity_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 5 = mas grave
    color: Mapped[str] = mapped_column(String(7), nullable=False)  # color en el mapa


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created','in_review','published','verified','rejected')", name="ck_report_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    neighborhood_id: Mapped[int] = mapped_column(ForeignKey("neighborhoods.id"), nullable=False, index=True)
    incident_type_id: Mapped[int] = mapped_column(ForeignKey("incident_types.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="created", nullable=False, index=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    # Lo que devolvio el componente de IA al analizar el reporte
    ai_suggested_type_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incident_types.id"))
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)
    ai_zone_risk: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(lazy="joined")
    neighborhood: Mapped[Neighborhood] = relationship(lazy="joined")
    incident_type: Mapped[IncidentType] = relationship(foreign_keys=[incident_type_id], lazy="joined")
    ai_suggested_type: Mapped[Optional[IncidentType]] = relationship(foreign_keys=[ai_suggested_type_id], lazy="joined")
    photos: Mapped[List["ReportPhoto"]] = relationship(back_populates="report", cascade="all, delete-orphan", lazy="selectin")


class ReportPhoto(Base):
    __tablename__ = "report_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report: Mapped[Report] = relationship(back_populates="photos")


class ReportStatusHistory(Base):
    """Cada fila es un elemento de la PILA de estados del reporte."""

    __tablename__ = "report_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_status: Mapped[Optional[str]] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    note: Mapped[Optional[str]] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportVerification(Base):
    __tablename__ = "report_verifications"
    __table_args__ = (UniqueConstraint("report_id", "user_id", name="uq_verification_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "neighborhood_id", name="uq_subscription"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    neighborhood_id: Mapped[int] = mapped_column(ForeignKey("neighborhoods.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    neighborhood: Mapped[Neighborhood] = relationship(lazy="joined")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"))
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIAnalysis(Base):
    """Bitacora de cada llamada al componente de IA (modelo usado, tiempo, resultado)."""

    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_type: Mapped[str] = mapped_column(String(30), nullable=False)  # report, heatmap, summary
    report_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"))
    neighborhood_id: Mapped[Optional[int]] = mapped_column(ForeignKey("neighborhoods.id"))
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("neighborhood_id", "summary_date", name="uq_daily_summary"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    neighborhood_id: Mapped[int] = mapped_column(ForeignKey("neighborhoods.id", ondelete="CASCADE"), nullable=False)
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    reports_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RiskHotspot(Base):
    """Resultado del mapa de calor predictivo: riesgo por barrio, dia y franja horaria."""

    __tablename__ = "risk_hotspots"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_day_of_week"),
        CheckConstraint("hour_block BETWEEN 0 AND 3", name="ck_hour_block"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    neighborhood_id: Mapped[int] = mapped_column(ForeignKey("neighborhoods.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0 = lunes
    hour_block: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0:00-6, 1:6-12, 2:12-18, 3:18-24
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0..1
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
