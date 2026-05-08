"""
Kontakte-Router — Firmen und Personen (AP 1.4).

Endpunkte:
  GET    /kontakte/firmen           — Firmen auflisten (mit Personenzahl)
  POST   /kontakte/firmen           — Firma anlegen
  GET    /kontakte/firmen/{id}      — Firma mit Personen
  PATCH  /kontakte/firmen/{id}      — Firma aktualisieren
  POST   /kontakte/personen         — Person anlegen
  PATCH  /kontakte/personen/{id}    — Person aktualisieren
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/kontakte", tags=["kontakte"])


def _sp(db: Session, user: dict):
    slug = user.get("mandant_slug", "")
    if slug:
        db.execute(text(f"SET LOCAL search_path TO tenant_{slug}, shared, public"))


def _name(user: dict) -> str:
    return f"{user.get('vorname', '')} {user.get('nachname', '')}".strip() or "system"


def _projekt_id(db, projekt: str):
    row = db.execute(
        text("SELECT id FROM projekte WHERE kurz = :k AND NOT geloescht"), {"k": projekt},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Projekt '{projekt}' nicht gefunden.")
    return row["id"]


# --- Schemas ---

class FirmaErstellen(BaseModel):
    name: str
    kuerzel: str | None = None
    rolle: str | None = None
    adresse: str | None = None
    telefon: str | None = None
    email: str | None = None

class FirmaAktualisieren(BaseModel):
    name: str | None = None
    kuerzel: str | None = None
    rolle: str | None = None
    adresse: str | None = None
    telefon: str | None = None
    email: str | None = None

class PersonErstellen(BaseModel):
    firma_id: UUID
    vorname: str
    nachname: str
    rolle: str | None = None
    telefon: str | None = None
    email: str | None = None

class PersonAktualisieren(BaseModel):
    vorname: str | None = None
    nachname: str | None = None
    rolle: str | None = None
    telefon: str | None = None
    email: str | None = None


# ===================================================================
# FIRMEN
# ===================================================================

@router.get("/firmen")
def firmen_liste(
    user: CurrentUser,
    db: Session = Depends(get_db),
    projekt: str = Query(default="FLI"),
):
    _sp(db, user)
    pid = _projekt_id(db, projekt)

    rows = db.execute(
        text("""
            SELECT f.id, f.name, f.kuerzel, f.rolle, f.adresse, f.telefon, f.email,
                   f.erstellt_am,
                   (SELECT COUNT(*) FROM personen p WHERE p.firma_id = f.id AND NOT p.geloescht) AS anzahl_personen
            FROM firmen f
            WHERE f.projekt_id = :pid AND NOT f.geloescht
            ORDER BY f.name
        """),
        {"pid": pid},
    ).mappings().all()

    return {"firmen": [dict(r) for r in rows], "gesamt": len(rows)}


@router.post("/firmen", status_code=201)
def firma_erstellen(
    body: FirmaErstellen,
    user: CurrentUser,
    db: Session = Depends(get_db),
    projekt: str = Query(default="FLI"),
):
    _sp(db, user)
    pid = _projekt_id(db, projekt)

    row = db.execute(
        text("""
            INSERT INTO firmen (projekt_id, name, kuerzel, rolle, adresse, telefon, email, erstellt_von)
            VALUES (:pid, :name, :kuerzel, :rolle, :adresse, :telefon, :email, :ev)
            RETURNING id, name, kuerzel, rolle, adresse, telefon, email, erstellt_am
        """),
        {"pid": pid, "name": body.name, "kuerzel": body.kuerzel, "rolle": body.rolle,
         "adresse": body.adresse, "telefon": body.telefon, "email": body.email, "ev": _name(user)},
    ).mappings().first()
    db.commit()
    _sp(db, user)
    return dict(row)


@router.get("/firmen/{firma_id}")
def firma_detail(
    firma_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    _sp(db, user)

    firma = db.execute(
        text("SELECT id, name, kuerzel, rolle, adresse, telefon, email, erstellt_am FROM firmen WHERE id = :id AND NOT geloescht"),
        {"id": str(firma_id)},
    ).mappings().first()
    if not firma:
        raise HTTPException(status_code=404, detail="Firma nicht gefunden.")

    personen = db.execute(
        text("SELECT id, vorname, nachname, rolle, telefon, email, erstellt_am FROM personen WHERE firma_id = :fid AND NOT geloescht ORDER BY nachname, vorname"),
        {"fid": str(firma_id)},
    ).mappings().all()

    result = dict(firma)
    result["personen"] = [dict(p) for p in personen]
    return result


@router.patch("/firmen/{firma_id}")
def firma_aktualisieren(
    firma_id: UUID,
    body: FirmaAktualisieren,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    _sp(db, user)
    felder = body.model_dump(exclude_unset=True)
    if not felder:
        raise HTTPException(status_code=400, detail="Keine Felder angegeben.")

    sets = ["geaendert_am = NOW()", "geaendert_von = :ev"]
    params = {"id": str(firma_id), "ev": _name(user)}
    for k in ("name", "kuerzel", "rolle", "adresse", "telefon", "email"):
        if k in felder:
            sets.append(f"{k} = :{k}")
            params[k] = felder[k]

    db.execute(text(f"UPDATE firmen SET {', '.join(sets)} WHERE id = :id AND NOT geloescht"), params)
    db.commit()
    _sp(db, user)
    return firma_detail(firma_id, user, db)


# ===================================================================
# PERSONEN
# ===================================================================

@router.post("/personen", status_code=201)
def person_erstellen(
    body: PersonErstellen,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    _sp(db, user)

    row = db.execute(
        text("""
            INSERT INTO personen (firma_id, vorname, nachname, rolle, telefon, email, erstellt_von)
            VALUES (:fid, :vn, :nn, :rolle, :tel, :email, :ev)
            RETURNING id, vorname, nachname, rolle, telefon, email, erstellt_am
        """),
        {"fid": str(body.firma_id), "vn": body.vorname, "nn": body.nachname,
         "rolle": body.rolle, "tel": body.telefon, "email": body.email, "ev": _name(user)},
    ).mappings().first()
    db.commit()
    _sp(db, user)
    return dict(row)


@router.patch("/personen/{person_id}")
def person_aktualisieren(
    person_id: UUID,
    body: PersonAktualisieren,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    _sp(db, user)
    felder = body.model_dump(exclude_unset=True)
    if not felder:
        raise HTTPException(status_code=400, detail="Keine Felder angegeben.")

    sets = ["geaendert_am = NOW()", "geaendert_von = :ev"]
    params = {"id": str(person_id), "ev": _name(user)}
    for k in ("vorname", "nachname", "rolle", "telefon", "email"):
        if k in felder:
            sets.append(f"{k} = :{k}")
            params[k] = felder[k]

    db.execute(text(f"UPDATE personen SET {', '.join(sets)} WHERE id = :id AND NOT geloescht"), params)
    db.commit()
    _sp(db, user)

    row = db.execute(
        text("SELECT id, vorname, nachname, rolle, telefon, email FROM personen WHERE id = :id"),
        {"id": str(person_id)},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Person nicht gefunden.")
    return dict(row)
