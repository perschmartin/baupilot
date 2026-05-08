"""
Aufgaben-Router — API-Endpunkte fuer AP 1.3.

Alle Endpunkte erfordern CurrentUser (vollstaendig authentifiziert mit TOTP).
Mandant wird aus dem JWT-Payload aufgeloest.

Endpunkte:
  GET    /aufgaben              — Aufgaben auflisten (Filter: status, prioritaet)
  POST   /aufgaben              — Aufgabe erstellen
  GET    /aufgaben/meine        — Meine Aufgaben (zustaendig = ich)
  GET    /aufgaben/{id}         — Aufgabe mit Kommentaren
  PATCH  /aufgaben/{id}         — Aufgabe aktualisieren
  POST   /aufgaben/{id}/kommentar — Kommentar hinzufuegen
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

from aufgaben.schemas import (
    AufgabeAktualisieren,
    AufgabeDetailResponse,
    AufgabeErstellen,
    AufgabenListeResponse,
    AufgabeResponse,
    KommentarErstellen,
    KommentarResponse,
)
from aufgaben.service import AufgabenError, AufgabenService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/aufgaben", tags=["aufgaben"])


def _get_service(db: Session = Depends(get_db), user: dict = Depends(get_current_user)) -> AufgabenService:
    return AufgabenService(db=db, mandant_slug=user.get("mandant_slug", ""))


def _benutzer_name(user: dict) -> str:
    """Vollstaendigen Benutzernamen aus JWT-Payload zusammensetzen."""
    return f"{user.get('vorname', '')} {user.get('nachname', '')}".strip() or user.get("email", "unbekannt")


# ===================================================================
# AUFGABEN AUFLISTEN
# ===================================================================

@router.get("/", response_model=AufgabenListeResponse)
def aufgaben_liste(
    user: CurrentUser,
    service: AufgabenService = Depends(_get_service),
    status: str | None = Query(default=None, pattern=r"^(offen|in_bearbeitung|geprueft|abgeschlossen|storniert)$"),
    prioritaet: str | None = Query(default=None, pattern=r"^(kritisch|hoch|mittel|niedrig)$"),
    projekt: str = Query(default="FLI"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Aufgaben des Projekts auflisten."""
    try:
        return service.liste_aufgaben(
            projekt_kurz=projekt,
            status=status,
            prioritaet=prioritaet,
            limit=limit,
            offset=offset,
        )
    except AufgabenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# MEINE AUFGABEN
# ===================================================================

@router.get("/meine", response_model=AufgabenListeResponse)
def meine_aufgaben(
    user: CurrentUser,
    service: AufgabenService = Depends(_get_service),
    status: str | None = Query(default=None),
    projekt: str = Query(default="FLI"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Aufgaben, bei denen ich zustaendig bin."""
    try:
        return service.liste_aufgaben(
            projekt_kurz=projekt,
            status=status,
            zustaendig_benutzer_id=UUID(user["sub"]),
            limit=limit,
            offset=offset,
        )
    except AufgabenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# AUFGABE ERSTELLEN
# ===================================================================

@router.post("/", response_model=AufgabeResponse, status_code=201)
def aufgabe_erstellen(
    body: AufgabeErstellen,
    user: CurrentUser,
    service: AufgabenService = Depends(_get_service),
    projekt: str = Query(default="FLI"),
):
    """Neue Aufgabe anlegen und optional delegieren."""
    try:
        return service.erstelle_aufgabe(
            projekt_kurz=projekt,
            gegenstand=body.gegenstand,
            erstellt_von_id=UUID(user["sub"]),
            erstellt_von_name=_benutzer_name(user),
            beschreibung=body.beschreibung,
            prioritaet=body.prioritaet,
            zustaendig_benutzer_id=body.zustaendig_benutzer_id,
            frist=str(body.frist) if body.frist else None,
            bauteil_id=body.bauteil_id,
            lv_id=body.lv_id,
            verantwortlich_firma_id=body.verantwortlich_firma_id,
            kosten_eur=body.kosten_eur,
            zeit_arbeitstage=body.zeit_arbeitstage,
            qualitaet_bewertung=body.qualitaet_bewertung,
        )
    except AufgabenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# AUFGABE DETAIL
# ===================================================================

@router.get("/{aufgabe_id}", response_model=AufgabeDetailResponse)
def aufgabe_detail(
    aufgabe_id: UUID,
    user: CurrentUser,
    service: AufgabenService = Depends(_get_service),
):
    """Aufgabe mit Kommentar-Thread laden."""
    try:
        return service.lade_aufgabe(aufgabe_id)
    except AufgabenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# AUFGABE AKTUALISIEREN
# ===================================================================

@router.patch("/{aufgabe_id}", response_model=AufgabeDetailResponse)
def aufgabe_aktualisieren(
    aufgabe_id: UUID,
    body: AufgabeAktualisieren,
    user: CurrentUser,
    service: AufgabenService = Depends(_get_service),
):
    """Aufgabe aktualisieren (Felder und/oder Status)."""
    felder = body.model_dump(exclude_unset=True)
    if not felder:
        raise HTTPException(status_code=400, detail="Keine Felder zum Aktualisieren angegeben.")

    try:
        return service.aktualisiere_aufgabe(
            aufgabe_id=aufgabe_id,
            benutzer_id=UUID(user["sub"]),
            benutzer_name=_benutzer_name(user),
            **felder,
        )
    except AufgabenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# KOMMENTAR HINZUFUEGEN
# ===================================================================

@router.post("/{aufgabe_id}/kommentar", response_model=KommentarResponse, status_code=201)
def kommentar_erstellen(
    aufgabe_id: UUID,
    body: KommentarErstellen,
    user: CurrentUser,
    service: AufgabenService = Depends(_get_service),
):
    """Kommentar an Aufgabe anfuegen (nicht loeschbar, G2)."""
    try:
        return service.erstelle_kommentar(
            aufgabe_id=aufgabe_id,
            autor_id=UUID(user["sub"]),
            autor_name=_benutzer_name(user),
            inhalt=body.inhalt,
        )
    except AufgabenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
