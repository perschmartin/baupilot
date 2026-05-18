"""Maengel-Router (AP 2.2c)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

from maengel.schemas import (
    MaengelListe,
    MaengelStatistik,
    MangelDetailResponse,
    MangelUpdate,
    PruefschrittAbschliessen,
)
from maengel.service import MangelError, MangelService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/maengel", tags=["maengel"])


def _get_service(db: Session = Depends(get_db), user: dict = Depends(get_current_user)) -> MangelService:
    return MangelService(db=db, mandant_slug=user.get("mandant_slug", ""))


def _benutzer_name(user: dict) -> str:
    return f"{user.get('vorname', '')} {user.get('nachname', '')}".strip() or user.get("email", "unbekannt")


def _benutzer_rollen(db: Session, user_id: str) -> set[str]:
    rows = db.execute(
        text("SELECT rolle FROM shared.benutzer_projekt_rollen WHERE benutzer_id = :uid"),
        {"uid": user_id},
    ).mappings().all()
    return {r["rolle"] for r in rows}


@router.get("/", response_model=MaengelListe)
def liste(
    user: CurrentUser,
    service: MangelService = Depends(_get_service),
    projekt: str = Query(default="FLI"),
    status: str | None = Query(default=None),
    mangelart: str | None = Query(default=None),
    suche: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        return service.lade_liste(projekt_kurz=projekt, status=status, mangelart=mangelart, suche=suche, limit=limit, offset=offset)
    except MangelError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/statistik", response_model=MaengelStatistik)
def statistik(
    user: CurrentUser,
    service: MangelService = Depends(_get_service),
    projekt: str = Query(default="FLI"),
):
    try:
        return service.statistik(projekt_kurz=projekt)
    except MangelError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/{mangel_id}", response_model=MangelDetailResponse)
def detail(
    mangel_id: UUID,
    user: CurrentUser,
    service: MangelService = Depends(_get_service),
):
    try:
        return service.lade_detail(mangel_id)
    except MangelError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.patch("/{mangel_id}", response_model=MangelDetailResponse)
def update(
    mangel_id: UUID,
    body: MangelUpdate,
    user: CurrentUser,
    service: MangelService = Depends(_get_service),
):
    """Mangelart, Kostenuntergliederung, Gewaehrleistungsverlaengerung anpassen."""
    try:
        return service.update(
            mangel_id=mangel_id,
            benutzer_name=_benutzer_name(user),
            mangelart=body.mangelart,
            verlaengerung_monate=body.verlaengerung_monate,
            nachtragsfolge_eur=body.nachtragsfolge_eur,
            folgekosten_betrieb_eur=body.folgekosten_betrieb_eur,
            minderkosten_eur=body.minderkosten_eur,
        )
    except MangelError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/{mangel_id}/schritt/{schritt_nr}", response_model=MangelDetailResponse)
def schritt_abschliessen(
    mangel_id: UUID,
    schritt_nr: int,
    body: PruefschrittAbschliessen,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: MangelService = Depends(_get_service),
):
    if not 1 <= schritt_nr <= 5:
        raise HTTPException(status_code=400, detail="Schritt muss zwischen 1 und 5 liegen.")
    rollen = _benutzer_rollen(db, user["sub"])
    try:
        return service.schritt_abschliessen(
            mangel_id=mangel_id,
            schritt_nr=schritt_nr,
            benutzer_id=user["sub"],
            benutzer_name=_benutzer_name(user),
            ergebnis=body.ergebnis,
            benutzer_rollen=rollen,
        )
    except MangelError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
