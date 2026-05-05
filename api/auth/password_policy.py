"""
Passwort-Richtlinie — lokale Staerke-Pruefung.

Aus dem 2FA-Toolkit uebernommen und angepasst:
  - HIBP-API-Check ENTFERNT (G2: keine externen APIs zur Laufzeit)
  - Stattdessen: lokale Pruefung gegen common_passwords.txt
  - Triviale Muster auf BauPilot-Kontext angepasst
  - Mindestlaenge auf 12 Zeichen erhoeht (NIST SP 800-63B)

Abhaengigkeiten: keine (Pure Python, Datei-I/O fuer Passwortliste)
"""

from __future__ import annotations

import logging
from pathlib import Path

from auth.constants import PASSWORT_MAX_LAENGE, PASSWORT_MIN_LAENGE, TRIVIALE_MUSTER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common-Passwords-Liste (lazy loaded)
# ---------------------------------------------------------------------------

_common_passwords: set[str] | None = None
_PASSWORDS_FILE = Path(__file__).parent.parent / "data" / "common_passwords.txt"


def _lade_common_passwords() -> set[str]:
    """Laedt die Liste haeufiger Passwoerter (lazy, einmalig)."""
    global _common_passwords
    if _common_passwords is not None:
        return _common_passwords

    try:
        text = _PASSWORDS_FILE.read_text(encoding="utf-8")
        _common_passwords = {
            line.strip().lower()
            for line in text.splitlines()
            if line.strip() and not line.startswith("#")
        }
        logger.info(
            "Common-Passwords-Liste geladen: %d Eintraege", len(_common_passwords)
        )
    except FileNotFoundError:
        logger.warning(
            "common_passwords.txt nicht gefunden unter %s — "
            "Pruefung gegen haeufige Passwoerter deaktiviert",
            _PASSWORDS_FILE,
        )
        _common_passwords = set()

    return _common_passwords


# ---------------------------------------------------------------------------
# Passwort-Pruefung
# ---------------------------------------------------------------------------

def pruefe_passwort_staerke(passwort: str) -> list[str]:
    """
    Lokale Passwort-Qualitaetspruefung.

    Returns:
        Liste von Fehlermeldungen (leer = OK).
    """
    fehler: list[str] = []

    if len(passwort) < PASSWORT_MIN_LAENGE:
        fehler.append(
            f"Mindestens {PASSWORT_MIN_LAENGE} Zeichen erforderlich "
            f"(aktuell: {len(passwort)})."
        )

    if len(passwort) > PASSWORT_MAX_LAENGE:
        fehler.append(
            f"Maximal {PASSWORT_MAX_LAENGE} Zeichen erlaubt."
        )

    if passwort.isdigit():
        fehler.append("Passwort darf nicht nur aus Ziffern bestehen.")

    if passwort.isalpha():
        fehler.append("Passwort sollte nicht nur aus Buchstaben bestehen.")

    # Triviale Muster pruefen
    lower = passwort.lower()
    for muster in TRIVIALE_MUSTER:
        if muster in lower:
            fehler.append(
                f"Passwort enthaelt ein zu haeufiges Muster ('{muster}')."
            )
            break

    # Gegen Common-Passwords-Liste pruefen
    common = _lade_common_passwords()
    if common and lower in common:
        fehler.append(
            "Dieses Passwort steht auf der Liste haeufig kompromittierter Passwoerter."
        )

    return fehler
