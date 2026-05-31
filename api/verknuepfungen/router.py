"""Verknuepfungsanalyse-Router (E12, B-002).

Endpunkte:
  GET  /verknuepfungen/{id}/vorschlaege    — Bestehende + neue Vorschlaege laden
  POST /verknuepfungen/{id}/analysieren     — Deterministische + LLM-Analyse starten
  POST /verknuepfungen/{id}/bestaetigen     — B-002 Gate: Vorschlag annehmen
  POST /verknuepfungen/{id}/ablehnen        — B-002 Gate: Vorschlag ablehnen
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser
from database import get_db
from verknuepfungen.service import (
    bestaetige_verknuepfung,
    finde_verknuepfungen_deterministisch,
    finde_verknuepfungen_llm,
    lade_vorschlaege,
    lehne_verknuepfung_ab,
    speichere_vorschlaege,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/verknuepfungen", tags=["verknuepfungen"])

TENANT_SCHEMA = "tenant_tlbv"


def _set_search_path(db: Session) -> None:
    """Setzt search_path auf tenant_tlbv (wie ergebnis-Modul)."""
    db.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, shared, public"))


def _vorgang_existiert(db: Session, vorgang_id: UUID) -> bool:
    row = db.execute(
        text("SELECT 1 FROM vorgaenge WHERE id = :id AND NOT geloescht"),
        {"id": str(vorgang_id)},
    ).first()
    return row is not None


@router.get("/{vorgang_id}/vorschlaege")
def verknuepfungs_vorschlaege(
    vorgang_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Bestehende Verknuepfungen und unbestaetigte Vorschlaege laden."""
    _set_search_path(db)
    if not _vorgang_existiert(db, vorgang_id):
        raise HTTPException(status_code=404, detail="Vorgang nicht gefunden.")

    return {
        "vorgang_id": str(vorgang_id),
        "verknuepfungen": lade_vorschlaege(db, vorgang_id),
    }


@router.post("/{vorgang_id}/analysieren")
def verknuepfung_analysieren(
    vorgang_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    mit_llm: bool = True,
):
    """Startet die Verknuepfungsanalyse (deterministisch + optional LLM).

    Ergebnis wird als llm_vorschlag in der DB gespeichert.
    Mensch muss per /bestaetigen oder /ablehnen entscheiden (B-002).
    """
    _set_search_path(db)
    if not _vorgang_existiert(db, vorgang_id):
        raise HTTPException(status_code=404, detail="Vorgang nicht gefunden.")

    # Schritt 1: Deterministisch
    vorschlaege = finde_verknuepfungen_deterministisch(db, vorgang_id)
    methode = "deterministisch"

    # Schritt 2: LLM (optional)
    if mit_llm:
        try:
            vorschlaege = finde_verknuepfungen_llm(db, vorgang_id, vorschlaege)
            methode = "deterministisch+llm"
        except Exception as e:
            logger.warning("LLM-Verknuepfungsanalyse fehlgeschlagen: %s", e)
            methode = "deterministisch (LLM fehlgeschlagen)"

    # Schritt 3: Vorschlaege speichern
    gespeichert = speichere_vorschlaege(db, vorgang_id, vorschlaege, user["sub"])

    return {
        "vorgang_id": str(vorgang_id),
        "methode": methode,
        "vorschlaege": vorschlaege,
        "neu_gespeichert": gespeichert,
        "hinweis": "Vorschlaege per /bestaetigen oder /ablehnen bewerten (B-002).",
    }


@router.post("/{vorgang_id}/bestaetigen")
def verknuepfung_bestaetigen(
    vorgang_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """B-002 Gate: Verknuepfungsvorschlag als 'ursache' bestaetigen."""
    _set_search_path(db)
    if not _vorgang_existiert(db, vorgang_id):
        raise HTTPException(status_code=404, detail="Vorgang nicht gefunden.")

    ok = bestaetige_verknuepfung(db, vorgang_id, user["sub"])
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Kein unbestaetigter LLM-Vorschlag an diesem Vorgang.",
        )

    return {"vorgang_id": str(vorgang_id), "status": "bestaetigt"}


@router.post("/{vorgang_id}/ablehnen")
def verknuepfung_ablehnen(
    vorgang_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """B-002 Gate: Verknuepfungsvorschlag ablehnen (Verknuepfung entfernen)."""
    _set_search_path(db)
    if not _vorgang_existiert(db, vorgang_id):
        raise HTTPException(status_code=404, detail="Vorgang nicht gefunden.")

    ok = lehne_verknuepfung_ab(db, vorgang_id, user["sub"])
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Kein unbestaetigter LLM-Vorschlag an diesem Vorgang.",
        )

    return {"vorgang_id": str(vorgang_id), "status": "abgelehnt"}
