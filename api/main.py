"""BauPilot — API-Einstiegspunkt.

Digitale Projektsteuerung fuer oeffentliche Hochbauprojekte.
Nachnutzung der SPARK-Module des BMDS.
"""

import time
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, create_shared_schema
from middleware import AuditLogMiddleware, TenantMiddleware
from routers import health, tenants
from auth import auth_router
from aufgaben import aufgaben_router
from vorgaenge import vorgaenge_router
from kontakte import kontakte_router
from dokumente import dokumente_router
from lv_extraktion import lv_router
from nachtraege import nachtraege_router
from behinderungen import behinderungen_router
from bedenken import bedenken_router
from maengel import maengel_router
from benachrichtigungen import benachrichtigungen_router
from tags import tags_router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger()
py_logger = logging.getLogger("baupilot")


# --- Retry-Fix: Warte auf PostgreSQL ---

def wait_for_database(max_retries: int = 15, delay: float = 2.0):
    """Wartet bis PostgreSQL erreichbar ist. Verhindert API-Crash bei Container-Neustart."""
    from sqlalchemy import text

    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
            py_logger.info(
                f"Datenbankverbindung hergestellt (Versuch {attempt}/{max_retries})"
            )
            return
        except Exception as e:
            if attempt < max_retries:
                py_logger.warning(
                    f"Datenbank nicht erreichbar (Versuch {attempt}/{max_retries}): {e}. "
                    f"Neuer Versuch in {delay}s..."
                )
                time.sleep(delay)
            else:
                py_logger.error(
                    f"Datenbank nach {max_retries} Versuchen nicht erreichbar. "
                    f"API-Start abgebrochen."
                )
                raise RuntimeError(
                    f"PostgreSQL nicht erreichbar nach {max_retries} Versuchen"
                ) from e


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: DB-Retry + Schema-Initialisierung. Shutdown: Engine dispose."""
    logger.info("startup", environment=settings.environment)
    wait_for_database()
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
    version="0.2.0",
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
app.include_router(aufgaben_router)
app.include_router(vorgaenge_router)
app.include_router(kontakte_router)
app.include_router(dokumente_router)
app.include_router(lv_router)
app.include_router(nachtraege_router)
app.include_router(behinderungen_router)
app.include_router(bedenken_router)
app.include_router(maengel_router)
app.include_router(benachrichtigungen_router)
app.include_router(tags_router)
