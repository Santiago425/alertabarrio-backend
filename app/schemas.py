"""Esquemas Pydantic: lo que entra y sale de la API."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth
class RegisterIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    phone: Optional[str] = Field(default=None, max_length=30)
    neighborhood_id: Optional[int] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class NeighborhoodOut(ORM):
    id: int
    name: str
    city: str
    latitude: float
    longitude: float


class UserOut(ORM):
    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    role: str
    neighborhood: Optional[NeighborhoodOut] = None
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --------------------------------------------------------------- catalogo
class IncidentTypeOut(ORM):
    id: int
    code: str
    name: str
    severity_level: int
    color: str


class ConnectionOut(BaseModel):
    from_id: int
    to_id: int
    distance_meters: float
    road_name: Optional[str] = None


# --------------------------------------------------------------- reportes
class ReportIn(BaseModel):
    title: str = Field(min_length=4, max_length=150)
    description: str = Field(min_length=10, max_length=2000)
    incident_type_id: int
    neighborhood_id: int
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    occurred_at: Optional[datetime] = None
    photo_url: Optional[str] = Field(default=None, max_length=500)


class StatusEntryOut(BaseModel):
    id: int
    previous_status: Optional[str]
    new_status: str
    changed_by: Optional[int]
    note: Optional[str]
    changed_at: datetime


class AIResultOut(BaseModel):
    available: bool
    model: Optional[str] = None
    suggested_type: Optional[IncidentTypeOut] = None
    confidence: Optional[float] = None
    zone_risk: Optional[float] = None
    matches_user_choice: Optional[bool] = None
    top_predictions: List[Dict[str, Any]] = []


class ReportOut(BaseModel):
    id: int
    title: str
    description: str
    latitude: float
    longitude: float
    occurred_at: datetime
    created_at: datetime
    status: str
    priority_score: float
    neighborhood: NeighborhoodOut
    incident_type: IncidentTypeOut
    reporter_name: str
    photos: List[str] = []
    ai_suggested_type: Optional[IncidentTypeOut] = None
    ai_confidence: Optional[float] = None
    ai_zone_risk: Optional[float] = None
    confirmations: Optional[int] = None


class ReportCreatedOut(BaseModel):
    report: ReportOut
    ai: AIResultOut
    queue_position: int
    queue_size: int


class VerifyIn(BaseModel):
    is_confirmed: bool = True
    comment: Optional[str] = Field(default=None, max_length=255)


class ModerationActionIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=255)


class UndoOut(BaseModel):
    report: ReportOut
    undone_status: str
    current_status: str
    stack: List[StatusEntryOut]


# ------------------------------------------------------- notificaciones
class NotificationOut(ORM):
    id: int
    report_id: Optional[int]
    message: str
    is_read: bool
    created_at: datetime


class SubscriptionOut(BaseModel):
    neighborhood: NeighborhoodOut
    created_at: datetime


# -------------------------------------------------------------------- IA
class HotspotOut(BaseModel):
    neighborhood_id: int
    neighborhood_name: str
    day_of_week: int
    hour_block: int
    risk_score: float


class HeatCellOut(BaseModel):
    latitude: float
    longitude: float
    intensity: float


class HeatmapOut(BaseModel):
    available: bool
    model: str
    reports_analyzed: int
    cells: List[HeatCellOut]
    hotspots: List[HotspotOut]
    neighborhood_risk: List[Dict[str, Any]]
    insights: List[str]


class SummaryOut(BaseModel):
    available: bool
    neighborhood: NeighborhoodOut
    summary_date: date
    reports_count: int
    summary_text: str
    model: str
    cached: bool = False


# ----------------------------------------------------------------- rutas
class RouteOut(BaseModel):
    from_neighborhood: NeighborhoodOut
    to_neighborhood: NeighborhoodOut
    safe_path: List[NeighborhoodOut]
    safe_path_meters: float
    shortest_path: List[NeighborhoodOut]
    shortest_path_meters: float
    fewest_hops_path: List[NeighborhoodOut]
    avoided: List[Dict[str, Any]]
    explanation: str
