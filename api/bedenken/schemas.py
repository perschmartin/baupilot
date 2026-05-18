"""Pydantic-Schemas fuer Bedenken-Endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Bedenken-Vorgang
# ---------------------------------------------------------------------------

class BedenkenResponse(BaseModel):
    """Bedenkenanzeige in Listen- und Detailansicht.

    Bedenken-spezifisch gegenueber Behinderungen: lv_id (zugeordnetes LV),
    gewaehrleistung_bis (Auswirkung auf Gewaehrleistung dokumentiert).
    """
    id: UUID
    nummer: str
    gegenstand: str
    beschreibung: str | None = None
    status: str
    prioritaet: str | None = None
    # Stoerungsfelder
    kosten_eur: float | None = None
    zeit_arbeitstage: int | None = None
    qualitaet_bewertung: str | None = None
    # Verantwortung & Bauteil
    verantwortlich_firma_id: UUID | None = None
    bauteil_id: UUID | None = None
    frist: date | None = None
    # Bedenken-spezifisch: LV-Position + Gewaehrleistung
    lv_id: UUID | None = None
    gewaehrleistung_bis: date | None = None
    # Audit
    erstellt_am: datetime
    erstellt_von: str | None = None
    geaendert_am: datetime | None = None


class BedenkenListe(BaseModel):
    """Paginierte Liste."""
    bedenken: list[BedenkenResponse]
    gesamt: int


# ---------------------------------------------------------------------------
# Pruefschritt (analog bedenkenpruefung — 6 Schritte)
# ---------------------------------------------------------------------------

class BedenkenPruefschrittResponse(BaseModel):
    id: UUID
    schritt: int
    titel: str
    ergebnis: str | None = None
    bearbeiter_id: UUID | None = None
    abgeschlossen: bool = False
    abgeschlossen_am: datetime | None = None
    ki_eingabe: Any | None = None
    ki_ergebnis: Any | None = None
    ki_konfidenz: float | None = None
    ki_bestaetigt: bool | None = None
    ki_bestaetigt_von: UUID | None = None
    ki_bestaetigt_am: datetime | None = None
    erstellt_am: datetime
    erstellt_von: UUID


class BedenkenDetailResponse(BedenkenResponse):
    pruefschritte: list[BedenkenPruefschrittResponse] = []
    aktueller_schritt: int = 0


class PruefschrittAbschliessen(BaseModel):
    ergebnis: str = Field(min_length=1, max_length=10000)


class BedenkenUpdate(BaseModel):
    """Optionale Stammdaten-Anpassung — bisher nur gewaehrleistung_bis.

    Wird durch PATCH /bedenken/{id} bedient. lv_id-Zuordnung bleibt
    derzeit beim Import-Zeitpunkt fixiert; eine Aenderung per UI kommt
    in einer spaeteren Etappe.
    """
    gewaehrleistung_bis: date | None = None


# ---------------------------------------------------------------------------
# Statistik
# ---------------------------------------------------------------------------

class StatistikGruppe(BaseModel):
    schluessel: str
    anzahl: int
    summe_kosten_eur: float = 0.0
    summe_zeit_arbeitstage: int = 0


class BedenkenStatistik(BaseModel):
    gesamt: int
    nach_status: list[StatistikGruppe]
    nach_firma: list[StatistikGruppe]
    summe_kosten_eur: float = 0.0
    summe_zeit_arbeitstage: int = 0
