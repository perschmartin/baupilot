"""Pydantic-Schemas fuer Behinderungen-Endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Behinderungs-Vorgang
# ---------------------------------------------------------------------------

class BehinderungResponse(BaseModel):
    """Behinderungsanzeige in Listen- und Detailansicht."""
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
    # Audit
    erstellt_am: datetime
    erstellt_von: str | None = None
    geaendert_am: datetime | None = None


class BehinderungenListe(BaseModel):
    """Paginierte Liste."""
    behinderungen: list[BehinderungResponse]
    gesamt: int


# ---------------------------------------------------------------------------
# Pruefschritt (analog zu nachtragspruefung — 6 Schritte)
# ---------------------------------------------------------------------------

class BehinderungPruefschrittResponse(BaseModel):
    """Ein Schritt im 6-Schritte-Workflow."""
    id: UUID
    schritt: int
    titel: str
    ergebnis: str | None = None
    bearbeiter_id: UUID | None = None
    abgeschlossen: bool = False
    abgeschlossen_am: datetime | None = None
    # KI-Felder (vorbereitet, derzeit noch nicht aktiv genutzt)
    ki_eingabe: Any | None = None
    ki_ergebnis: Any | None = None
    ki_konfidenz: float | None = None
    ki_bestaetigt: bool | None = None
    ki_bestaetigt_von: UUID | None = None
    ki_bestaetigt_am: datetime | None = None
    # Audit
    erstellt_am: datetime
    erstellt_von: UUID


class BehinderungDetailResponse(BehinderungResponse):
    """Behinderung mit allen Pruefschritten."""
    pruefschritte: list[BehinderungPruefschrittResponse] = []
    aktueller_schritt: int = 0


class PruefschrittAbschliessen(BaseModel):
    """Body fuer Schritt-Abschluss."""
    ergebnis: str = Field(min_length=1, max_length=10000)


# ---------------------------------------------------------------------------
# Aggregation (Dashboard-Endpunkt)
# ---------------------------------------------------------------------------

class StatistikGruppe(BaseModel):
    """Eine Aggregations-Gruppe (z.B. nach Status)."""
    schluessel: str
    anzahl: int
    summe_kosten_eur: float = 0.0
    summe_zeit_arbeitstage: int = 0


class BehinderungenStatistik(BaseModel):
    """Aggregation zur Anzeige im Dashboard."""
    gesamt: int
    nach_status: list[StatistikGruppe]
    nach_firma: list[StatistikGruppe]
    summe_kosten_eur: float = 0.0
    summe_zeit_arbeitstage: int = 0
