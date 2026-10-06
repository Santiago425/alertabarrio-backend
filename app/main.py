"""
AlertaBarrio API - Backend del proyecto final de Estructuras de Datos.

Arranque local:
    uvicorn app.main:app --reload --port 8000
Documentacion interactiva (Swagger): http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import SessionLocal
from .routers import ai, auth, catalog, general, moderation, notifications, reports, routes
from .seed import init_db
from .services.engine import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    init_db(with_seed=settings.seed_on_startup)
    db = SessionLocal()
    try:
        engine.load(db)  # cargamos las estructuras de datos desde PostgreSQL
    finally:
        db.close()
    logging.getLogger("alertabarrio").info(
        "Estructuras cargadas: %s pendientes en la cola, %s barrios en el grafo",
        len(engine.moderation_queue),
        engine.city_graph.vertex_count,
    )
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Reportes de seguridad ciudadana con estructuras de datos propias e IA.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (general, auth, catalog, reports, moderation, notifications, routes, ai):
    app.include_router(r.router)


@app.get("/", include_in_schema=False)
def root():
    return {"message": "AlertaBarrio API", "docs": "/docs", "hello": "/api/v1/hello"}
