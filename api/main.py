"""BauPilot — API-Einstiegspunkt.

Digitale Projektsteuerung fuer oeffentliche Hochbauprojekte.
Nachnutzung der SPARK-Module des BMDS.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, create_shared_schema
from middleware import AuditLogMiddleware, TenantMiddleware
from routers import health, tenants
from auth import auth_router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: Schema-Initialisierung. Shutdown: Engine dispose."""
    logger.info("startup", environment=settings.environment)
    create_shared_schema()
    yield
    engine.dispose()
    logger.info("shutdown")


app = FastAPI(
    title="BauPilot API",
    description=(
        "Digitale Projektsteuerung fuer oeffentliche Hochbauprojekte. "
        "Nachnutzung der SPARK-Module des BMDS."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# --- Middleware ---

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(TenantMiddleware)

# --- Router ---

app.include_router(health.router)
app.include_router(tenants.router, prefix="/api/v1")
app.include_router(auth_router)
