"""
MFA (Multi-Faktor-Authentifizierung) — TOTP-basiert.

Uebernommen und angepasst aus dem 2FA-Toolkit (familienstiftung.software):
  - TOTP_ISSUER auf "BauPilot" gesetzt
  - Backup-Code-Alphabet ohne verwechselbare Zeichen (0/O, 1/I/L)
  - TOTP-Secrets werden verschluesselt gespeichert (siehe security.py)

Ablauf:
  1. User aktiviert MFA ueber POST /api/v1/auth/totp/setup
  2. User bestaetigt mit erstem TOTP-Code
  3. Beim Login: nach Passwort-Check kommt TOTP-Abfrage
  4. Backup-Codes als Einmal-Codes falls Authenticator verloren

Abhaengigkeiten: pyotp, qrcode[pil], argon2-cffi
"""

from __future__ import annotations

import base64
import io
import secrets

import pyotp
import qrcode  # type: ignore[import-untyped]
import qrcode.constants  # type: ignore[import-untyped]

from auth.constants import (
    BACKUP_CODE_ALPHABET,
    BACKUP_CODE_ANZAHL,
    BACKUP_CODE_LAENGE,
    TOTP_DIGITS,
    TOTP_INTERVAL,
    TOTP_ISSUER,
    TOTP_VALID_WINDOW,
)
from auth.security import hash_passwort, verify_passwort


# ---------------------------------------------------------------------------
# TOTP-Kern
# ---------------------------------------------------------------------------

def generiere_totp_secret() -> str:
    """Erzeugt ein neues TOTP-Secret (Base32, 32 Zeichen)."""
    return pyotp.random_base32(length=32)


def erstelle_totp_uri(secret: str, email: str) -> str:
    """Erzeugt die otpauth:// URI fuer den Authenticator."""
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
    return totp.provisioning_uri(name=email, issuer_name=TOTP_ISSUER)


def generiere_qr_data_uri(otpauth_uri: str) -> str:
    """
    Erzeugt einen QR-Code als Base64-Data-URI (PNG).

    Aus dem 2FA-Toolkit uebernommen — bewaehrte Implementierung.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=4,
    )
    qr.add_data(otpauth_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def verifiziere_totp(secret: str, code: str) -> bool:
    """Prueft einen TOTP-Code (mit Toleranz fuer Clock-Drift)."""
    if not code or not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
    return totp.verify(code, valid_window=TOTP_VALID_WINDOW)


# ---------------------------------------------------------------------------
# Backup-Codes
# Aus dem 2FA-Toolkit: Verwechselbare Zeichen (0/O, 1/I/L) ausgeschlossen.
# ---------------------------------------------------------------------------

def generiere_backup_codes() -> list[str]:
    """
    Erzeugt BACKUP_CODE_ANZAHL Einmal-Codes im Klartext.

    Format: 8 alphanumerische Zeichen ohne verwechselbare Zeichen.
    Werden dem Benutzer genau einmal angezeigt.
    """
    return [
        "".join(secrets.choice(BACKUP_CODE_ALPHABET) for _ in range(BACKUP_CODE_LAENGE))
        for _ in range(BACKUP_CODE_ANZAHL)
    ]


def hash_backup_codes(codes: list[str]) -> list[str]:
    """Hasht alle Backup-Codes mit Argon2id fuer DB-Speicherung."""
    return [hash_passwort(code) for code in codes]


def verifiziere_backup_code(code: str, gehashte_codes: list[str]) -> int | None:
    """
    Prueft ob ein Code mit einem der gehashten Codes uebereinstimmt.

    Returns:
        Index des passenden Codes (zum Entfernen) oder None.
    """
    normalisiert = code.strip().upper()
    for idx, hashed in enumerate(gehashte_codes):
        if verify_passwort(normalisiert, hashed):
            return idx
    return None
