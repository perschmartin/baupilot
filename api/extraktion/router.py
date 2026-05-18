"""Extraktor-Router (E13b)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db
from extraktion.service import (
    ExtraktionError,
    lade_pdf_text,
    llm_extrahiere,
    speichere_ergebnis_in_pruefschritt,
    uebernehme_in_vorgang,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/extraktion", tags=["extraktion"])


def _vorgangstyp(db: Session, vorgang_id: UUID) -> str:
    """Liefert den Vorgangstyp (behinderungsanzeige|bedenkenanzeige|mangelanzeige|nachtrag|aufgabe)."""
    row = db.execute(
        text("SELECT typ::text AS typ FROM vorgaenge WHERE id = :id AND NOT geloescht"),
        {"id": str(vorgang_id)},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Vorgang nicht gefunden.")
    return row["typ"]


@router.post("/{vorgang_id}/vorschlag")
def extraktion_vorschlag(
    vorgang_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """LLM-Extraktion aus dem verknuepften PDF starten und Vorschlag liefern.

    Schritte:
      1. Pruefen ob Vorgang existiert und Typ unterstuetzt wird (Stoerungstypen).
      2. PDF aus MinIO laden, Text extrahieren.
      3. LLM-Call gegen Qwen 32B.
      4. Ergebnis im Pruefschritt 1 als ki_ergebnis speichern (Audit-Trail).
      5. Vorschlag als JSON an Anwender zurueckgeben — der entscheidet, ob er ihn uebernimmt.
    """
    typ = _vorgangstyp(db, vorgang_id)
    if typ not in ("behinderungsanzeige", "bedenkenanzeige", "mangelanzeige"):
        raise HTTPException(
            status_code=400,
            detail=f"Extraktion derzeit nur fuer Stoerungstypen, nicht fuer '{typ}'.",
        )

    try:
        pdf_text, meta = lade_pdf_text(db, vorgang_id)
        if not pdf_text.strip():
            raise HTTPException(status_code=400, detail="Aus dem PDF konnte kein Text extrahiert werden.")
        ergebnis = llm_extrahiere(pdf_text)
        speichere_ergebnis_in_pruefschritt(
            db=db, vorgang_id=vorgang_id, typ=typ,
            extrahiert=ergebnis, eingabe_meta=meta,
            benutzer_id=user["sub"],
        )
    except ExtraktionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    return {
        "vorgang_id": vorgang_id,
        "typ": typ,
        "dokument": meta,
        "vorschlag": ergebnis,
        "hinweis": "Vorschlag noch nicht uebernommen. Per /uebernehmen bestaetigen.",
    }


@router.post("/{vorgang_id}/uebernehmen")
def extraktion_uebernehmen(
    vorgang_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Nimmt den im Pruefschritt 1 gespeicherten Vorschlag und schreibt die
    Felder in den Vorgangs-Datensatz. COALESCE schuetzt vorhandene Werte —
    nur leere Felder werden befuellt.
    """
    typ = _vorgangstyp(db, vorgang_id)
    if typ not in ("behinderungsanzeige", "bedenkenanzeige", "mangelanzeige"):
        raise HTTPException(status_code=400, detail=f"Uebernahme nicht fuer Typ '{typ}'.")

    # ki_ergebnis aus dem passenden Pruefschritt 1 holen
    tabelle = {
        "behinderungsanzeige": "behinderungspruefung",
        "bedenkenanzeige": "bedenkenpruefung",
        "mangelanzeige": "mangelpruefung",
    }[typ]
    row = db.execute(
        text(f"SELECT ki_ergebnis FROM {tabelle} WHERE vorgang_id = :vid AND schritt = 1"),
        {"vid": str(vorgang_id)},
    ).mappings().first()
    if not row or not row["ki_ergebnis"]:
        raise HTTPException(status_code=404, detail="Kein LLM-Vorschlag im Pruefschritt 1 gespeichert.")

    extrahiert = row["ki_ergebnis"]
    benutzer_name = f"{user.get('vorname', '')} {user.get('nachname', '')}".strip() or user.get("email", "unbekannt")

    try:
        uebernehme_in_vorgang(
            db=db, vorgang_id=vorgang_id,
            extrahiert=extrahiert, benutzer_name=benutzer_name,
        )
    except ExtraktionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    return {"vorgang_id": vorgang_id, "status": "uebernommen", "felder": extrahiert}
