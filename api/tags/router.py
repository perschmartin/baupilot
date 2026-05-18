"""Tag-Router (B-013, Roadmap E11)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["tags"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TagResponse(BaseModel):
    id: UUID
    projekt_id: UUID
    kategorie: str
    wert: str
    parent_id: UUID | None = None
    ist_kategorie_wurzel: bool = False


class TagListe(BaseModel):
    tags: list[TagResponse]
    gesamt: int


class DokumentTagRequest(BaseModel):
    tag_id: UUID


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tags", response_model=TagListe)
def liste(
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Alle Tags des aktuellen Mandanten — flach, mit parent_id fuer Hierarchie-Aufbau.

    Frontend baut den Forest (Wurzeln → Kinder) lokal aus dieser Liste.
    Sortierung: Wurzeln zuerst, dann Kinder nach Wert.
    """
    rows = db.execute(
        text("""
            SELECT id, projekt_id, kategorie, wert, parent_id, ist_kategorie_wurzel
            FROM tags
            ORDER BY ist_kategorie_wurzel DESC, kategorie, wert
        """),
    ).mappings().all()
    return {"tags": [dict(r) for r in rows], "gesamt": len(rows)}


@router.post("/dokumente/{dokument_id}/tags")
def dokument_tag_hinzufuegen(
    dokument_id: UUID,
    body: DokumentTagRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Tag an Dokument haengen. Idempotent (ON CONFLICT DO NOTHING)."""
    # Validierung: existiert Dokument? existiert Tag?
    dok = db.execute(
        text("SELECT id FROM dokumente WHERE id = :id AND NOT geloescht"),
        {"id": str(dokument_id)},
    ).mappings().first()
    if not dok:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")
    tag = db.execute(
        text("SELECT id FROM tags WHERE id = :id"),
        {"id": str(body.tag_id)},
    ).mappings().first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag nicht gefunden.")

    benutzer_name = f"{user.get('vorname', '')} {user.get('nachname', '')}".strip() or user.get("email", "unbekannt")
    db.execute(
        text("""
            INSERT INTO dokument_tags (dokument_id, tag_id, erstellt_von)
            VALUES (:did, :tid, :ben)
            ON CONFLICT (dokument_id, tag_id) DO NOTHING
        """),
        {"did": str(dokument_id), "tid": str(body.tag_id), "ben": benutzer_name},
    )
    db.commit()
    return {"status": "ok"}


@router.delete("/dokumente/{dokument_id}/tags/{tag_id}")
def dokument_tag_entfernen(
    dokument_id: UUID,
    tag_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Tag-Zuordnung loesen. Liefert ok auch wenn die Verknuepfung nicht existiert."""
    db.execute(
        text("DELETE FROM dokument_tags WHERE dokument_id = :did AND tag_id = :tid"),
        {"did": str(dokument_id), "tid": str(tag_id)},
    )
    db.commit()
    return {"status": "ok"}


@router.get("/dokumente/{dokument_id}/tags", response_model=TagListe)
def dokument_tags_lesen(
    dokument_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Tags eines Dokuments."""
    rows = db.execute(
        text("""
            SELECT t.id, t.projekt_id, t.kategorie, t.wert, t.parent_id, t.ist_kategorie_wurzel
            FROM dokument_tags dt
            JOIN tags t ON t.id = dt.tag_id
            WHERE dt.dokument_id = :did
            ORDER BY t.kategorie, t.wert
        """),
        {"did": str(dokument_id)},
    ).mappings().all()
    return {"tags": [dict(r) for r in rows], "gesamt": len(rows)}
