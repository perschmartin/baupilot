"""
Login-Rate-Limiting — Brute-Force-Schutz.

Zwei Verteidigungslinien:
  1. In-Memory Sliding Window (schnell, aus dem 2FA-Toolkit)
     - IP-basiert: max 10 Versuche pro 15 Minuten
     - Account-basiert: max 5 Versuche pro 15 Minuten
  2. DB-basierte progressive Sperrung (persistent, BauPilot-spezifisch)
     - fehlversuche / gesperrt_bis auf der benutzer-Tabelle
     - Sperrdauer eskaliert mit jedem Schwellwert

Die In-Memory-Schicht faengt Brute-Force ab, bevor die DB belastet wird.
Die DB-Schicht ueberlebt Container-Restarts.

Abhaengigkeiten: keine (Pure Python)
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from auth.constants import (
    RATE_LIMIT_ACCOUNT_FENSTER,
    RATE_LIMIT_ACCOUNT_MAX,
    RATE_LIMIT_IP_FENSTER,
    RATE_LIMIT_IP_MAX,
    SPERRSTUFEN,
)


# ---------------------------------------------------------------------------
# Sliding-Window-Tracker (aus 2FA-Toolkit, unveraendert)
# ---------------------------------------------------------------------------

@dataclass
class _SlidingWindow:
    """Zaehlt Ereignisse in einem gleitenden Zeitfenster."""
    window_seconds: int
    max_events: int
    _buckets: dict[str, deque] = field(
        default_factory=lambda: defaultdict(deque)
    )

    def _cleanup(self, key: str, now: float) -> None:
        bucket = self._buckets[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def record(self, key: str) -> None:
        now = time.monotonic()
        self._cleanup(key, now)
        self._buckets[key].append(now)

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        self._cleanup(key, now)
        return len(self._buckets[key]) >= self.max_events

    def count(self, key: str) -> int:
        now = time.monotonic()
        self._cleanup(key, now)
        return len(self._buckets[key])

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


# Globale Tracker-Instanzen
_ip_tracker = _SlidingWindow(
    window_seconds=RATE_LIMIT_IP_FENSTER,
    max_events=RATE_LIMIT_IP_MAX,
)

_account_tracker = _SlidingWindow(
    window_seconds=RATE_LIMIT_ACCOUNT_FENSTER,
    max_events=RATE_LIMIT_ACCOUNT_MAX,
)


# ---------------------------------------------------------------------------
# In-Memory Rate-Limit API
# ---------------------------------------------------------------------------

def pruefe_rate_limit(ip: str, email: str) -> str | None:
    """
    Prueft ob ein Login-Versuch erlaubt ist (In-Memory).

    Returns:
        None wenn erlaubt, sonst Grund ("ip" oder "account").
    """
    if _ip_tracker.is_blocked(ip):
        return "ip"
    if _account_tracker.is_blocked(email.lower()):
        return "account"
    return None


def erfasse_fehlversuch(ip: str, email: str) -> None:
    """Zeichnet einen fehlgeschlagenen Login-Versuch auf."""
    _ip_tracker.record(ip)
    _account_tracker.record(email.lower())


def erfasse_erfolg(ip: str, email: str) -> None:
    """Setzt den Account-Zaehler nach erfolgreichem Login zurueck."""
    _account_tracker.reset(email.lower())
    # IP-Tracker NICHT zuruecksetzen — Brute-Force auf andere Accounts


def verbleibende_versuche(ip: str, email: str) -> dict[str, int]:
    """Gibt die verbleibenden Versuche zurueck (fuer Logging/Debug)."""
    return {
        "ip_verbleibend": max(0, RATE_LIMIT_IP_MAX - _ip_tracker.count(ip)),
        "account_verbleibend": max(
            0, RATE_LIMIT_ACCOUNT_MAX - _account_tracker.count(email.lower())
        ),
    }


# ---------------------------------------------------------------------------
# DB-basierte progressive Sperrung (Hilfsfunktionen)
# Die eigentliche DB-Interaktion liegt in service.py.
# ---------------------------------------------------------------------------

def berechne_sperrdauer(fehlversuche: int) -> timedelta | None:
    """
    Berechnet die Sperrdauer basierend auf der Anzahl Fehlversuche.

    Returns:
        timedelta fuer die Sperre oder None wenn keine Sperre noetig.
    """
    sperrdauer_sekunden = 0
    for schwelle, dauer in sorted(SPERRSTUFEN.items()):
        if fehlversuche >= schwelle:
            sperrdauer_sekunden = dauer
    if sperrdauer_sekunden > 0:
        return timedelta(seconds=sperrdauer_sekunden)
    return None


def ist_gesperrt(gesperrt_bis: datetime | None) -> bool:
    """Prueft ob ein Account aktuell gesperrt ist."""
    if gesperrt_bis is None:
        return False
    return datetime.now(timezone.utc) < gesperrt_bis
