"""BauPilot — Health-Check-Endpunkte."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    """Pruefen, ob API und Datenbank erreichbar sind."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": "baupilot-api",
        "version": "0.2.0",
        "database": db_status,
    }


@router.get("/")
def root() -> dict:
    """Basis-Endpunkt."""
    return {
        "service": "BauPilot API",
        "version": "0.2.0",
        "docs": "/docs",
    }
