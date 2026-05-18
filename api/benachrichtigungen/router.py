"""Benachrichtigungen-Router (B-012, Roadmap E10)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

from benachrichtigungen.schemas import (
    BenachrichtigungenListe,
    UngelesenAntwort,
)
from benachrichtigungen.service import BenachrichtigungError, BenachrichtigungsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/benachrichtigungen", tags=["benachrichtigungen"])


def _get_service(db: Session = Depends(get_db), user: dict = Depends(get_current_user)) -> BenachrichtigungsService:
    return BenachrichtigungsService(db=db, mandant_slug=user.get("mandant_slug", ""))


@router.get("/", response_model=BenachrichtigungenListe)
def liste(
    user: CurrentUser,
    service: BenachrichtigungsService = Depends(_get_service),
    nur_ungelesen: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.liste(
        benutzer_id=UUID(user["sub"]),
        nur_ungelesen=nur_ungelesen,
        limit=limit,
        offset=offset,
    )


@router.get("/ungelesen-anzahl", response_model=UngelesenAntwort)
def ungelesen_anzahl(
    user: CurrentUser,
    service: BenachrichtigungsService = Depends(_get_service),
):
    """Leichtgewichtiges Polling fuer das Bell-Badge."""
    return {"ungelesen": service.ungelesen_anzahl(benutzer_id=UUID(user["sub"]))}


@router.post("/{benachrichtigung_id}/gelesen")
def markiere_gelesen(
    benachrichtigung_id: UUID,
    user: CurrentUser,
    service: BenachrichtigungsService = Depends(_get_service),
):
    service.markiere_gelesen(
        benutzer_id=UUID(user["sub"]),
        benachrichtigung_id=benachrichtigung_id,
    )
    return {"status": "ok"}


@router.post("/alle-gelesen")
def markiere_alle_gelesen(
    user: CurrentUser,
    service: BenachrichtigungsService = Depends(_get_service),
):
    """Alle ungelesenen Benachrichtigungen des Benutzers als gelesen markieren."""
    count = service.markiere_alle_gelesen(benutzer_id=UUID(user["sub"]))
    return {"status": "ok", "markiert": count}
