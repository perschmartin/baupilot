"""
FastAPI-Dependencies v2 — TOTP-Pflicht erzwungen.

Drei Token-Typen:
  1. totp_setup_required=True  — Benutzer muss TOTP einrichten (nur Setup-Routen)
  2. totp_pending=True         — TOTP aktiv, Code noch nicht eingegeben (nur Verify-Route)
  3. Normal                    — Vollzugang

get_current_user blockiert Typ 1 und 2.
get_setup_user akzeptiert Typ 1 (fuer TOTP-Setup und Passwort-Aenderung).
get_totp_pending_user akzeptiert Typ 2 (fuer TOTP-Verify beim Login).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.security import validiere_access_token
from config import settings
from database import get_db

logger = logging.getLogger(__name__)


def _extrahiere_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:]
    return None


def _validiere_und_extrahiere(request: Request) -> dict[str, Any]:
    """Gemeinsame Token-Validierung fuer alle Dependencies."""
    token = _extrahiere_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    payload = validiere_access_token(token, settings.jwt_secret)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token ungueltig oder abgelaufen.")
    return payload


# ---------------------------------------------------------------------------
# Vollzugang — nur mit aktivem TOTP
# ---------------------------------------------------------------------------

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Vollstaendig authentifizierter Benutzer.
    Blockiert wenn TOTP nicht eingerichtet oder Code ausstehend.
    """
    payload = _validiere_und_extrahiere(request)

    if payload.get("totp_setup_required"):
        raise HTTPException(
            status_code=403,
            detail="2FA muss zuerst eingerichtet werden (POST /api/v1/auth/totp/setup).",
        )

    if payload.get("totp_pending"):
        raise HTTPException(
            status_code=401,
            detail="2FA-Code erforderlich (POST /api/v1/auth/totp/verify).",
        )

    mandant_slug = payload.get("mandant_slug")
    if mandant_slug:
        db.execute(text(f"SET LOCAL search_path TO tenant_{mandant_slug}, shared, public"))

    return payload


# ---------------------------------------------------------------------------
# TOTP-Setup — fuer Benutzer die TOTP einrichten muessen
# ---------------------------------------------------------------------------

def get_setup_user(
    request: Request,
) -> dict[str, Any]:
    """
    Benutzer der TOTP einrichten oder Passwort aendern muss.
    Akzeptiert Tokens mit totp_setup_required=True.
    Akzeptiert auch vollwertige Tokens (fuer nachtraegliches TOTP-Setup).
    """
    payload = _validiere_und_extrahiere(request)

    if payload.get("totp_pending"):
        raise HTTPException(
            status_code=401,
            detail="2FA-Code erforderlich, nicht Setup.",
        )

    return payload


# ---------------------------------------------------------------------------
# TOTP-Pending — fuer Login mit aktivem TOTP
# ---------------------------------------------------------------------------

def get_totp_pending_user(
    request: Request,
) -> dict[str, Any]:
    """Benutzer im TOTP-Pending-Status (Login-Flow Schritt 2)."""
    payload = _validiere_und_extrahiere(request)

    if not payload.get("totp_pending"):
        raise HTTPException(status_code=400, detail="Kein TOTP-Pending-Status.")

    return payload


# ---------------------------------------------------------------------------
# Rollen
# ---------------------------------------------------------------------------

def require_role(*erlaubte_rollen: str):
    def _check(
        request: Request,
        user: dict[str, Any] = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        result = db.execute(
            text("SELECT rolle FROM shared.benutzer_projekt_rollen WHERE benutzer_id = :bid"),
            {"bid": user["sub"]},
        )
        rollen = {r[0] for r in result.all()}
        if not rollen.intersection(erlaubte_rollen):
            raise HTTPException(status_code=403, detail="Keine Berechtigung.")
        return user
    return _check


RequireAdmin = Depends(require_role("admin"))


# ---------------------------------------------------------------------------
# AuthService-Factory
# ---------------------------------------------------------------------------

def get_auth_service(db: Session = Depends(get_db)):
    from auth.service import AuthService
    return AuthService(db=db)


# Type-Aliases
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
SetupUser = Annotated[dict[str, Any], Depends(get_setup_user)]
TotpPendingUser = Annotated[dict[str, Any], Depends(get_totp_pending_user)]
