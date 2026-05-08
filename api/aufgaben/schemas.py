"""
Pydantic v2 Schemas fuer das Aufgabenmanagement (AP 1.3).

Dreiklang-Felder (G3): kosten_eur, zeit_arbeitstage, qualitaet_bewertung
sind Pflichtdimensionen an jedem Vorgang.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Aufgabe erstellen
# ---------------------------------------------------------------------------

class AufgabeErstellen(BaseModel):
    """Neue Aufgabe anlegen."""
    gegenstand: str = Field(min_length=1, max_length=1000)
    beschreibung: str | None = None
    prioritaet: str = Field(default="mittel", pattern=r"^(kritisch|hoch|mittel|niedrig)$")
    zustaendig_benutzer_id: UUID | None = None
    frist: date | None = None
    bauteil_id: UUID | None = None
    lv_id: UUID | None = None
    verantwortlich_firma_id: UUID | None = None
    # Dreiklang (G3)
    kosten_eur: float | None = None
    zeit_arbeitstage: int | None = None
    qualitaet_bewertung: str | None = None


# ---------------------------------------------------------------------------
# Aufgabe aktualisieren
# ---------------------------------------------------------------------------

class AufgabeAktualisieren(BaseModel):
    """Felder einer Aufgabe aktualisieren."""
    gegenstand: str | None = Field(default=None, min_length=1, max_length=1000)
    beschreibung: str | None = None
    prioritaet: str | None = Field(default=None, pattern=r"^(kritisch|hoch|mittel|niedrig)$")
    status: str | None = Field(default=None, pattern=r"^(offen|in_bearbeitung|geprueft|abgeschlossen|storniert)$")
    zustaendig_benutzer_id: UUID | None = None
    frist: date | None = None
    bauteil_id: UUID | None = None
    lv_id: UUID | None = None
    verantwortlich_firma_id: UUID | None = None
    # Dreiklang (G3)
    kosten_eur: float | None = None
    zeit_arbeitstage: int | None = None
    qualitaet_bewertung: str | None = None


# ---------------------------------------------------------------------------
# Aufgabe lesen
# ---------------------------------------------------------------------------

class AufgabeResponse(BaseModel):
    """Aufgabe in der Listenansicht."""
    id: UUID
    nummer: str
    gegenstand: str
    beschreibung: str | None = None
    prioritaet: str
    status: str
    frist: date | None = None
    zustaendig_benutzer_id: UUID | None = None
    zustaendig_name: str | None = None
    delegiert_von_benutzer_id: UUID | None = None
    delegiert_von_name: str | None = None
    verantwortlich_firma_id: UUID | None = None
    # Dreiklang
    kosten_eur: float | None = None
    zeit_arbeitstage: int | None = None
    qualitaet_bewertung: str | None = None
    erstellt_am: datetime
    geaendert_am: datetime | None = None
    erstellt_von: str


# ---------------------------------------------------------------------------
# Kommentar
# ---------------------------------------------------------------------------

class KommentarErstellen(BaseModel):
    """Neuen Kommentar an einer Aufgabe anlegen."""
    inhalt: str = Field(min_length=1, max_length=10000)


class KommentarResponse(BaseModel):
    """Kommentar in der Detailansicht."""
    id: UUID
    autor_id: UUID
    autor_name: str
    inhalt: str
    erstellt_am: datetime


# ---------------------------------------------------------------------------
# Aufgabe mit Kommentaren
# ---------------------------------------------------------------------------

class AufgabeDetailResponse(AufgabeResponse):
    """Aufgabe mit Kommentarthread."""
    kommentare: list[KommentarResponse] = []


# ---------------------------------------------------------------------------
# Listen-Response
# ---------------------------------------------------------------------------

class AufgabenListeResponse(BaseModel):
    """Paginierte Aufgabenliste."""
    aufgaben: list[AufgabeResponse]
    gesamt: int
