"""Bedenken-Router (AP 2.2b)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

from bedenken.schemas import (
    BedenkenDetailResponse,
    BedenkenListe,
    BedenkenStatistik,
    BedenkenUpdate,
    PruefschrittAbschliessen,
)
from bedenken.service import BedenkenError, BedenkenService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bedenken", tags=["bedenken"])


def _get_service(db: Session = Depends(get_db), user: dict = Depends(get_current_user)) -> BedenkenService:
    return BedenkenService(db=db, mandant_slug=user.get("mandant_slug", ""))


def _benutzer_name(user: dict) -> str:
    return f"{user.get('vorname', '')} {user.get('nachname', '')}".strip() or user.get("email", "unbekannt")


def _benutzer_rollen(db: Session, user_id: str) -> set[str]:
    rows = db.execute(
        text("SELECT rolle FROM shared.benutzer_projekt_rollen WHERE benutzer_id = :uid"),
        {"uid": user_id},
    ).mappings().all()
    return {r["rolle"] for r in rows}


@router.get("/", response_model=BedenkenListe)
def liste(
    user: CurrentUser,
    service: BedenkenService = Depends(_get_service),
    projekt: str = Query(default="FLI"),
    status: str | None = Query(default=None),
    lv_id: UUID | None = Query(default=None),
    suche: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        return service.lade_liste(projekt_kurz=projekt, status=status, lv_id=lv_id, suche=suche, limit=limit, offset=offset)
    except BedenkenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/statistik", response_model=BedenkenStatistik)
def statistik(
    user: CurrentUser,
    service: BedenkenService = Depends(_get_service),
    projekt: str = Query(default="FLI"),
):
    try:
        return service.statistik(projekt_kurz=projekt)
    except BedenkenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/{bedenken_id}", response_model=BedenkenDetailResponse)
def detail(
    bedenken_id: UUID,
    user: CurrentUser,
    service: BedenkenService = Depends(_get_service),
):
    try:
        return service.lade_detail(bedenken_id)
    except BedenkenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.patch("/{bedenken_id}", response_model=BedenkenDetailResponse)
def update(
    bedenken_id: UUID,
    body: BedenkenUpdate,
    user: CurrentUser,
    service: BedenkenService = Depends(_get_service),
):
    """Stammdaten anpassen. Aktuell nur gewaehrleistung_bis editierbar."""
    try:
        return service.update(
            bedenken_id=bedenken_id,
            benutzer_name=_benutzer_name(user),
            gewaehrleistung_bis=body.gewaehrleistung_bis,
        )
    except BedenkenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/{bedenken_id}/schritt/{schritt_nr}", response_model=BedenkenDetailResponse)
def schritt_abschliessen(
    bedenken_id: UUID,
    schritt_nr: int,
    body: PruefschrittAbschliessen,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: BedenkenService = Depends(_get_service),
):
    if not 1 <= schritt_nr <= 6:
        raise HTTPException(status_code=400, detail="Schritt muss zwischen 1 und 6 liegen.")
    rollen = _benutzer_rollen(db, user["sub"])
    try:
        return service.schritt_abschliessen(
            bedenken_id=bedenken_id,
            schritt_nr=schritt_nr,
            benutzer_id=user["sub"],
            benutzer_name=_benutzer_name(user),
            ergebnis=body.ergebnis,
            benutzer_rollen=rollen,
        )
    except BedenkenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
