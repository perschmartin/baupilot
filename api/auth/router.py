"""
Auth-Router v2 — TOTP-Pflicht + Einladungssystem.

Endpunkte:
  POST /login              — Login (gibt eingeschraenktes Token ohne TOTP)
  POST /totp/verify        — TOTP-Code nach Login
  POST /totp/setup         — TOTP einrichten (auch mit eingeschraenktem Token)
  POST /totp/confirm       — TOTP-Setup bestaetigen
  POST /totp/disable       — TOTP deaktivieren
  POST /refresh            — Token-Rotation (nur mit TOTP)
  POST /logout             — Sitzung beenden
  POST /logout-all         — Alle Sitzungen beenden
  GET  /me                 — Profil (nur mit TOTP)
  POST /passwort           — Passwort aendern (auch mit eingeschraenktem Token)
  POST /admin/reset        — Admin-Passwort-Reset
  POST /einladung          — Admin generiert Einladung
  POST /registrieren       — Neuer Benutzer mit Einladungs-Token
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db

from auth.dependencies import (
    CurrentUser,
    RequireAdmin,
    SetupUser,
    TotpPendingUser,
    get_auth_service,
)
from auth.schemas import (
    AdminResetRequest,
    EinladungRequest,
    EinladungResponse,
    ErfolgResponse,
    LoginRequest,
    LoginResponse,
    PasswortAendernRequest,
    RefreshRequest,
    RegistrierungRequest,
    RegistrierungResponse,
    TokenResponse,
    TotpConfirmRequest,
    TotpConfirmResponse,
    TotpSetupResponse,
    TotpVerifyRequest,
)
from auth.service import AuthError, AuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


# === LOGIN ===

@router.post("/login", response_model=LoginResponse)
def login(request: Request, body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    try:
        result = service.login(
            email=body.email, passwort=body.passwort,
            ip_adresse=_client_ip(request), user_agent=_user_agent(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return result


# === TOTP VERIFY (Login-Flow Schritt 2) ===

@router.post("/totp/verify", response_model=TokenResponse)
def totp_verify(request: Request, body: TotpVerifyRequest, user: TotpPendingUser,
                service: AuthService = Depends(get_auth_service)):
    try:
        result = service.verifiziere_totp_login(
            benutzer_id=UUID(user["sub"]), code=body.code,
            ip_adresse=_client_ip(request), user_agent=_user_agent(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"access_token": result["access_token"], "refresh_token": result["refresh_token"]}


# === TOTP SETUP (erlaubt mit eingeschraenktem Token) ===

@router.post("/totp/setup", response_model=TotpSetupResponse)
def totp_setup(user: SetupUser, service: AuthService = Depends(get_auth_service)):
    try:
        return service.totp_setup(benutzer_id=UUID(user["sub"]))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/totp/confirm", response_model=TotpConfirmResponse)
def totp_confirm(request: Request, body: TotpConfirmRequest, user: SetupUser,
                 service: AuthService = Depends(get_auth_service)):
    try:
        codes = service.totp_confirm(
            benutzer_id=UUID(user["sub"]), code=body.code,
            ip_adresse=_client_ip(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"backup_codes": codes}


@router.post("/totp/disable", response_model=ErfolgResponse)
def totp_disable(request: Request, body: PasswortAendernRequest, user: CurrentUser,
                 service: AuthService = Depends(get_auth_service)):
    try:
        service.totp_deaktivieren(
            benutzer_id=UUID(user["sub"]),
            passwort=body.aktuelles_passwort,
            ip_adresse=_client_ip(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "ok", "meldung": "2FA deaktiviert."}


# === TOKEN REFRESH (nur mit aktivem TOTP) ===

@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, body: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return service.refresh_tokens(
            refresh_token_klartext=body.refresh_token,
            ip_adresse=_client_ip(request), user_agent=_user_agent(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# === LOGOUT ===

@router.post("/logout", response_model=ErfolgResponse)
def logout(request: Request, body: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    service.logout(refresh_token_klartext=body.refresh_token, ip_adresse=_client_ip(request))
    return {"status": "ok", "meldung": "Abgemeldet."}


@router.post("/logout-all", response_model=ErfolgResponse)
def logout_all(request: Request, user: CurrentUser, service: AuthService = Depends(get_auth_service)):
    count = service.logout_alle(benutzer_id=UUID(user["sub"]), ip_adresse=_client_ip(request))
    return {"status": "ok", "meldung": f"{count} Sitzung(en) beendet."}


# === PROFIL (nur mit aktivem TOTP) ===

@router.get("/me")
def me(user: CurrentUser, service: AuthService = Depends(get_auth_service)):
    try:
        return service.lade_profil(benutzer_id=UUID(user["sub"]))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# === BENUTZER-LISTE (AE-03 — Aufgaben-Zuweisung per Dropdown) ===

@router.get("/benutzer-liste")
def benutzer_liste(
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Listet aktive Benutzer fuer Zuweisungs-Dropdowns (AE-03).

    Liefert nur die im Frontend benoetigten Felder. Inaktive oder gesperrte
    Konten werden ausgeschlossen — sie sollen in einem Auswahl-Dropdown nicht
    erscheinen. Sortierung nach Nachname/Vorname fuer eine alphabetische Liste.
    """
    rows = db.execute(
        text("""
            SELECT id, vorname, nachname, email
            FROM shared.benutzer
            WHERE (gesperrt_bis IS NULL OR gesperrt_bis < NOW())
            ORDER BY nachname, vorname, email
        """),
    ).mappings().all()
    return {
        "benutzer": [
            {
                "id": r["id"],
                "vorname": r["vorname"] or "",
                "nachname": r["nachname"] or "",
                "email": r["email"],
                "anzeige_name": (
                    f"{(r['vorname'] or '').strip()} {(r['nachname'] or '').strip()}".strip()
                    or r["email"]
                ),
            }
            for r in rows
        ],
        "gesamt": len(rows),
    }


# === PASSWORT (erlaubt mit eingeschraenktem Token) ===

@router.post("/passwort", response_model=ErfolgResponse)
def passwort_aendern(request: Request, body: PasswortAendernRequest, user: SetupUser,
                     service: AuthService = Depends(get_auth_service)):
    try:
        service.passwort_aendern(
            benutzer_id=UUID(user["sub"]),
            aktuelles=body.aktuelles_passwort, neues=body.neues_passwort,
            ip_adresse=_client_ip(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "ok", "meldung": "Passwort geaendert."}


@router.post("/admin/reset", response_model=ErfolgResponse, dependencies=[RequireAdmin])
def admin_reset(request: Request, body: AdminResetRequest, user: CurrentUser,
                service: AuthService = Depends(get_auth_service)):
    try:
        service.admin_reset(
            admin_id=UUID(user["sub"]), benutzer_id=body.benutzer_id,
            neues=body.neues_passwort, ip_adresse=_client_ip(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "ok", "meldung": "Passwort zurueckgesetzt."}


# === EINLADUNG (nur Admin) ===

@router.post("/einladung", response_model=EinladungResponse, dependencies=[RequireAdmin])
def einladung_erstellen(request: Request, body: EinladungRequest, user: CurrentUser,
                        service: AuthService = Depends(get_auth_service)):
    try:
        return service.erstelle_einladung(
            admin_id=UUID(user["sub"]),
            email=body.email, rolle=body.rolle,
            mandant_slug=body.mandant_slug, projekt_kurz=body.projekt_kurz,
            gueltig_stunden=body.gueltig_stunden,
            ip_adresse=_client_ip(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# === REGISTRIERUNG (oeffentlich, aber nur mit Einladungs-Token) ===

@router.post("/registrieren", response_model=RegistrierungResponse)
def registrieren(request: Request, body: RegistrierungRequest,
                 service: AuthService = Depends(get_auth_service)):
    try:
        return service.registrieren(
            einladungs_token=body.einladungs_token,
            vorname=body.vorname, nachname=body.nachname,
            passwort=body.passwort, ip_adresse=_client_ip(request))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
