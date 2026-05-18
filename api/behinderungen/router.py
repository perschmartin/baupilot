"""Behinderungen-Router (AP 2.2a).

Endpoints:
  GET    /behinderungen/                — Liste (paginiert, gefiltert)
  GET    /behinderungen/statistik       — Aggregations-Dashboard
  GET    /behinderungen/{id}            — Detail mit Pruefschritten
  POST   /behinderungen/{id}/schritt/{nr} — Pruefschritt abschliessen
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

from behinderungen.schemas import (
    BehinderungDetailResponse,
    BehinderungenListe,
    BehinderungenStatistik,
    PruefschrittAbschliessen,
)
from behinderungen.service import BehinderungError, BehinderungService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/behinderungen", tags=["behinderungen"])


def _get_service(db: Session = Depends(get_db), user: dict = Depends(get_current_user)) -> BehinderungService:
    return BehinderungService(db=db, mandant_slug=user.get("mandant_slug", ""))


def _benutzer_name(user: dict) -> str:
    return f"{user.get('vorname', '')} {user.get('nachname', '')}".strip() or user.get("email", "unbekannt")


def _benutzer_rollen(db: Session, user_id: str) -> set[str]:
    rows = db.execute(
        text("SELECT rolle FROM shared.benutzer_projekt_rollen WHERE benutzer_id = :uid"),
        {"uid": user_id},
    ).mappings().all()
    return {r["rolle"] for r in rows}


# ===================================================================
# LISTE
# ===================================================================

@router.get("/", response_model=BehinderungenListe)
def liste(
    user: CurrentUser,
    service: BehinderungService = Depends(_get_service),
    projekt: str = Query(default="FLI"),
    status: str | None = Query(default=None),
    suche: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        return service.lade_liste(projekt_kurz=projekt, status=status, suche=suche, limit=limit, offset=offset)
    except BehinderungError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# STATISTIK — vor /{id}, damit "/statistik" nicht als UUID geparst wird
# ===================================================================

@router.get("/statistik", response_model=BehinderungenStatistik)
def statistik(
    user: CurrentUser,
    service: BehinderungService = Depends(_get_service),
    projekt: str = Query(default="FLI"),
):
    try:
        return service.statistik(projekt_kurz=projekt)
    except BehinderungError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# DETAIL
# ===================================================================

@router.get("/{behinderung_id}", response_model=BehinderungDetailResponse)
def detail(
    behinderung_id: UUID,
    user: CurrentUser,
    service: BehinderungService = Depends(_get_service),
):
    try:
        return service.lade_detail(behinderung_id)
    except BehinderungError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# SCHRITT ABSCHLIESSEN
# ===================================================================

@router.post("/{behinderung_id}/schritt/{schritt_nr}", response_model=BehinderungDetailResponse)
def schritt_abschliessen(
    behinderung_id: UUID,
    schritt_nr: int,
    body: PruefschrittAbschliessen,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: BehinderungService = Depends(_get_service),
):
    if not 1 <= schritt_nr <= 6:
        raise HTTPException(status_code=400, detail="Schritt muss zwischen 1 und 6 liegen.")
    rollen = _benutzer_rollen(db, user["sub"])
    try:
        return service.schritt_abschliessen(
            behinderung_id=behinderung_id,
            schritt_nr=schritt_nr,
            benutzer_id=user["sub"],
            benutzer_name=_benutzer_name(user),
            ergebnis=body.ergebnis,
            benutzer_rollen=rollen,
        )
    except BehinderungError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
