"""Pydantic-Schemas fuer Maengel-Endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# Werte des mangelart-Enums aus Migration 008
MangelartLiteral = Literal["ausfuehrungsmangel", "planungsmangel", "unklar"]


class MangelResponse(BaseModel):
    """Mangelanzeige in Listen- und Detailansicht."""
    id: UUID
    nummer: str
    gegenstand: str
    beschreibung: str | None = None
    status: str
    prioritaet: str | None = None
    # Standardfelder
    kosten_eur: float | None = None
    zeit_arbeitstage: int | None = None
    qualitaet_bewertung: str | None = None
    verantwortlich_firma_id: UUID | None = None
    bauteil_id: UUID | None = None
    frist: date | None = None
    # Mangel-spezifisch (Migration 008)
    mangelart: MangelartLiteral | None = None
    verlaengerung_monate: int | None = None
    # Kostenuntergliederung
    nachtragsfolge_eur: float | None = None
    folgekosten_betrieb_eur: float | None = None
    minderkosten_eur: float | None = None
    # Audit
    erstellt_am: datetime
    erstellt_von: str | None = None
    geaendert_am: datetime | None = None


class MaengelListe(BaseModel):
    maengel: list[MangelResponse]
    gesamt: int


class MangelPruefschrittResponse(BaseModel):
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


class MangelDetailResponse(MangelResponse):
    pruefschritte: list[MangelPruefschrittResponse] = []
    aktueller_schritt: int = 0


class PruefschrittAbschliessen(BaseModel):
    ergebnis: str = Field(min_length=1, max_length=10000)


class MangelUpdate(BaseModel):
    """Stammdaten-Update — Mangelart + Kostenuntergliederung + Verlaengerung.

    Alle Felder optional; nur uebergebene Werte werden geaendert.
    """
    mangelart: MangelartLiteral | None = None
    verlaengerung_monate: int | None = None
    nachtragsfolge_eur: float | None = None
    folgekosten_betrieb_eur: float | None = None
    minderkosten_eur: float | None = None


# ---------------------------------------------------------------------------
# Statistik
# ---------------------------------------------------------------------------

class StatistikGruppe(BaseModel):
    schluessel: str
    anzahl: int
    summe_kosten_eur: float = 0.0
    summe_zeit_arbeitstage: int = 0


class MaengelStatistik(BaseModel):
    """Mangel-Aggregation mit zusaetzlicher Aufschluesselung nach Mangelart."""
    gesamt: int
    nach_status: list[StatistikGruppe]
    nach_firma: list[StatistikGruppe]
    nach_mangelart: list[StatistikGruppe]
    summe_kosten_eur: float = 0.0
    summe_zeit_arbeitstage: int = 0
    summe_nachtragsfolge_eur: float = 0.0
    summe_folgekosten_betrieb_eur: float = 0.0
    summe_minderkosten_eur: float = 0.0
