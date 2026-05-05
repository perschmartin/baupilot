"""
Security-Kern — Passwort-Hashing, JWT, TOTP-Secret-Verschluesselung.

Reine Funktionen ohne Datenbankabhaengigkeit.
Unit-testbar und wiederverwendbar.

Integriert bewährte Patterns aus dem 2FA-Toolkit (familienstiftung.software)
mit BauPilot-spezifischen Erweiterungen:
  - AES-256-GCM Verschluesselung fuer TOTP-Secrets (Toolkit speichert Klartext)
  - JWT statt Cookie-Sessions
  - Kein externer API-Zugriff (G2)

Abhaengigkeiten: argon2-cffi, PyJWT, cryptography
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from auth.constants import JWT_ALGORITHMUS

# ---------------------------------------------------------------------------
# Passwort-Hashing (Argon2id)
# Identisch mit 2FA-Toolkit, bewaehrt in Produktion.
# ---------------------------------------------------------------------------

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_passwort(passwort: str) -> str:
    """Passwort mit Argon2id hashen."""
    return _hasher.hash(passwort)


def verify_passwort(passwort: str, hash_wert: str) -> bool:
    """Passwort gegen Hash pruefen. Gibt False bei Mismatch."""
    if not hash_wert or hash_wert == "":
        return False
    try:
        return _hasher.verify(hash_wert, passwort)
    except (VerifyMismatchError, VerificationError):
        return False


def braucht_rehash(hash_wert: str) -> bool:
    """Prueft, ob der Hash mit veralteten Parametern erstellt wurde."""
    if not hash_wert or hash_wert == "":
        return False
    return _hasher.check_needs_rehash(hash_wert)


# ---------------------------------------------------------------------------
# JWT (Access-Token und Refresh-Token)
# ---------------------------------------------------------------------------

def erstelle_access_token(
    payload: dict[str, Any],
    secret: str,
    lebensdauer_minuten: int = 15,
) -> str:
    """
    Erzeugt einen signierten JWT Access-Token.

    Payload enthaelt: benutzer_id, mandant_id, email, rollen.
    Kein sensitiver Inhalt (kein Passwort, kein TOTP-Secret).
    """
    now = datetime.now(timezone.utc)
    claims = {
        **payload,
        "iat": now,
        "exp": now + timedelta(minutes=lebensdauer_minuten),
        "typ": "access",
    }
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHMUS)


def erstelle_refresh_token() -> str:
    """
    Erzeugt einen kryptographisch sicheren Refresh-Token.

    Wird NICHT als JWT codiert, sondern als zufaelliger String.
    In der DB wird nur der SHA-256-Hash gespeichert.
    """
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    """Token hashen fuer DB-Speicherung (SHA-256, nicht reversibel)."""
    return hashlib.sha256(token.encode()).hexdigest()


def validiere_access_token(token: str, secret: str) -> dict[str, Any] | None:
    """
    Validiert einen JWT Access-Token.

    Returns:
        Payload-Dict bei Erfolg, None bei ungueltigem/abgelaufenem Token.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHMUS])
        if payload.get("typ") != "access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# TOTP-Secret-Verschluesselung (AES-256-GCM)
# Erweiterung gegenueber dem 2FA-Toolkit, das Klartext speichert.
# Ein DB-Dump allein genuegt damit nicht zur 2FA-Umgehung.
# ---------------------------------------------------------------------------

def verschluessele_totp_secret(secret: str, schluessel: str) -> str:
    """
    Verschluesselt ein TOTP-Secret mit AES-256-GCM.

    Args:
        secret: TOTP-Secret im Klartext (Base32).
        schluessel: Hex-codierter 256-Bit-Schluessel aus .env (BAUPILOT_TOTP_KEY).

    Returns:
        Hex-String: nonce (24 Hex) + ciphertext+tag (Rest).
    """
    key_bytes = bytes.fromhex(schluessel)
    if len(key_bytes) != 32:
        raise ValueError("TOTP-Schluessel muss 256 Bit (64 Hex-Zeichen) sein")

    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(12)  # 96 Bit Nonce fuer GCM
    ciphertext = aesgcm.encrypt(nonce, secret.encode("utf-8"), None)
    return nonce.hex() + ciphertext.hex()


def entschluessele_totp_secret(verschluesselt: str, schluessel: str) -> str:
    """
    Entschluesselt ein mit AES-256-GCM verschluesseltes TOTP-Secret.

    Args:
        verschluesselt: Hex-String aus verschluessele_totp_secret().
        schluessel: Hex-codierter 256-Bit-Schluessel aus .env.

    Returns:
        TOTP-Secret im Klartext (Base32).

    Raises:
        ValueError: Bei ungueltigem Schluessel oder manipulierten Daten.
    """
    key_bytes = bytes.fromhex(schluessel)
    if len(key_bytes) != 32:
        raise ValueError("TOTP-Schluessel muss 256 Bit (64 Hex-Zeichen) sein")

    nonce = bytes.fromhex(verschluesselt[:24])
    ciphertext = bytes.fromhex(verschluesselt[24:])

    aesgcm = AESGCM(key_bytes)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise ValueError("TOTP-Secret konnte nicht entschluesselt werden") from exc
