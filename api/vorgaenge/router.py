"""
Vorgaenge-Router — Read-only API fuer alle Vorgangtypen.

Zeigt importierte Nachtraege, Behinderungs-/Bedenkenanzeigen und Maengel.
Ergaenzt den Aufgaben-Router (AP 1.3), der nur typ='aufgabe' behandelt.

Endpunkte:
  GET /vorgaenge/          — Vorgaenge auflisten (Filter: typ, status)
  GET /vorgaenge/statistik — Anzahl pro Typ und Status
  GET /vorgaenge/{id}      — Einzelnen Vorgang laden
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/vorgaenge", tags=["vorgaenge"])


def _ensure_search_path(db: Session, user: dict):
    """search_path auf Tenant + shared + public setzen (Enums liegen in public)."""
    slug = user.get("mandant_slug", "")
    if slug:
        db.execute(text(f"SET LOCAL search_path TO tenant_{slug}, shared, public"))


# ===================================================================
# VORGAENGE AUFLISTEN
# ===================================================================

@router.get("/")
def vorgaenge_liste(
    user: CurrentUser,
    db: Session = Depends(get_db),
    typ: str | None = Query(default=None, description="nachtrag, behinderungsanzeige, bedenkenanzeige, mangelanzeige"),
    status: str | None = Query(default=None),
    suche: str | None = Query(default=None, description="Freitextsuche in Nummer und Gegenstand"),
    projekt: str = Query(default="FLI"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Vorgaenge eines Projekts auflisten. Ohne typ-Filter werden alle Typen geliefert."""
    _ensure_search_path(db, user)

    projekt_row = db.execute(
        text("SELECT id FROM projekte WHERE kurz = :kurz AND NOT geloescht"),
        {"kurz": projekt},
    ).mappings().first()
    if not projekt_row:
        raise HTTPException(status_code=404, detail=f"Projekt '{projekt}' nicht gefunden.")

    where_parts = ["v.projekt_id = :pid", "NOT v.geloescht"]
    params: dict = {"pid": projekt_row["id"]}

    if typ:
        where_parts.append("v.typ = CAST(:typ AS vorgangtyp)")
        params["typ"] = typ
    if status:
        where_parts.append("v.status = CAST(:status AS vorgangstatus)")
        params["status"] = status
    if suche:
        where_parts.append("(v.nummer ILIKE :suche OR v.gegenstand ILIKE :suche)")
        params["suche"] = f"%{suche}%"

    where = " AND ".join(where_parts)

    gesamt = db.execute(
        text(f"SELECT COUNT(*) FROM vorgaenge v WHERE {where}"), params,
    ).scalar()

    params["limit"] = limit
    params["offset"] = offset

    rows = db.execute(
        text(f"""
            SELECT v.id, v.typ::text, v.nummer, v.gegenstand, v.beschreibung,
                   v.status::text, v.prioritaet, v.frist,
                   v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                   v.erstellt_am, v.erstellt_von
            FROM vorgaenge v
            WHERE {where}
            ORDER BY v.nummer ASC
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).mappings().all()

    return {"vorgaenge": [dict(r) for r in rows], "gesamt": gesamt}


# ===================================================================
# STATISTIK
# ===================================================================

@router.get("/statistik")
def vorgaenge_statistik(
    user: CurrentUser,
    db: Session = Depends(get_db),
    projekt: str = Query(default="FLI"),
):
    """Anzahl Vorgaenge pro Typ und Status."""
    _ensure_search_path(db, user)

    rows = db.execute(
        text("""
            SELECT v.typ::text AS typ, v.status::text AS status, COUNT(*) AS anzahl
            FROM vorgaenge v
            JOIN projekte p ON p.id = v.projekt_id
            WHERE p.kurz = :kurz AND NOT v.geloescht
            GROUP BY v.typ, v.status
            ORDER BY v.typ, v.status
        """),
        {"kurz": projekt},
    ).mappings().all()

    return {"statistik": [dict(r) for r in rows]}


# ===================================================================
# VORGANG DETAIL
# ===================================================================

@router.get("/{vorgang_id}")
def vorgang_detail(
    vorgang_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Einzelnen Vorgang laden."""
    _ensure_search_path(db, user)

    row = db.execute(
        text("""
            SELECT v.id, v.typ::text, v.nummer, v.gegenstand, v.beschreibung,
                   v.status::text, v.prioritaet, v.frist,
                   v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                   v.erstellt_am, v.erstellt_von, v.geaendert_am, v.geaendert_von,
                   v.verantwortlich_firma_id, v.bauteil_id, v.lv_id
            FROM vorgaenge v
            WHERE v.id = :id AND NOT v.geloescht
        """),
        {"id": str(vorgang_id)},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Vorgang nicht gefunden.")

    result = dict(row)

    # Kommentare laden (falls vorhanden)
    kommentare = db.execute(
        text("""
            SELECT id, autor_id, autor_name, inhalt, erstellt_am
            FROM aufgaben_kommentare
            WHERE vorgang_id = :vid
            ORDER BY erstellt_am ASC
        """),
        {"vid": str(vorgang_id)},
    ).mappings().all()

    result["kommentare"] = [dict(k) for k in kommentare]
    return result
