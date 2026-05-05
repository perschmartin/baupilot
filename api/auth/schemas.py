"""
Pydantic v2 Schemas fuer das Auth-System.
v2: Einladungssystem + TOTP-Setup-Pflicht.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    passwort: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    erfordert_totp: bool = False
    erfordert_totp_setup: bool = False
    muss_passwort_aendern: bool = False


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str


# ---------------------------------------------------------------------------
# Passwort
# ---------------------------------------------------------------------------

class PasswortAendernRequest(BaseModel):
    aktuelles_passwort: str
    neues_passwort: str = Field(min_length=12, max_length=128)


class AdminResetRequest(BaseModel):
    benutzer_id: UUID
    neues_passwort: str = Field(min_length=12, max_length=128)


# ---------------------------------------------------------------------------
# TOTP-Setup
# ---------------------------------------------------------------------------

class TotpSetupResponse(BaseModel):
    qr_data_uri: str
    secret: str
    hinweis: str = "QR-Code scannen oder Secret manuell eingeben."


class TotpConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TotpConfirmResponse(BaseModel):
    backup_codes: list[str]
    hinweis: str = (
        "Diese Codes sicher aufbewahren. "
        "Jeder Code kann genau einmal verwendet werden."
    )


# ---------------------------------------------------------------------------
# Einladung + Registrierung
# ---------------------------------------------------------------------------

class EinladungRequest(BaseModel):
    email: EmailStr
    rolle: str = "leser"
    mandant_slug: str = "tlbv"
    projekt_kurz: str = "SYS"
    gueltig_stunden: int = Field(default=72, ge=1, le=720)


class EinladungResponse(BaseModel):
    einladungs_token: str
    email: str
    ablauf: datetime
    hinweis: str = "Diesen Token dem eingeladenen Benutzer mitteilen."


class RegistrierungRequest(BaseModel):
    einladungs_token: str
    vorname: str = Field(min_length=1, max_length=127)
    nachname: str = Field(min_length=1, max_length=127)
    passwort: str = Field(min_length=12, max_length=128)


class RegistrierungResponse(BaseModel):
    access_token: str
    erfordert_totp_setup: bool = True
    hinweis: str = "Konto erstellt. 2FA muss jetzt eingerichtet werden."


# ---------------------------------------------------------------------------
# Benutzer-Profil
# ---------------------------------------------------------------------------

class MandantInfo(BaseModel):
    id: UUID
    name: str
    slug: str


class BenutzerProfil(BaseModel):
    id: UUID
    email: str
    vorname: str
    nachname: str
    mandant: MandantInfo | None = None
    rollen: list[str]
    totp_aktiviert: bool
    letzter_login: datetime | None = None


# ---------------------------------------------------------------------------
# Allgemein
# ---------------------------------------------------------------------------

class ErfolgResponse(BaseModel):
    status: str = "ok"
    meldung: str = ""
