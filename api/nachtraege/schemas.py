"""
Pydantic v2 Schemas fuer das Nachtragsmanagement (AP 2.1).

Dreiklang-Felder (G8): kosten (betrag_gefordert/geprueft/genehmigt),
zeit (zeitauswirkung_tage), qualitaet (qualitaetsauswirkung).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Nachtrag CRUD
# ---------------------------------------------------------------------------

class NachtragErstellen(BaseModel):
    """Neuen Nachtrag manuell anlegen (neben den importierten)."""
    gegenstand: str = Field(min_length=1, max_length=1000)
    beschreibung: str | None = None
    betrag_gefordert: float | None = None
    zeitauswirkung_tage: int | None = None
    qualitaetsauswirkung: str | None = None
    lv_id: UUID | None = None
    kostengruppe_din276: str | None = Field(default=None, max_length=10)
    verantwortlich_firma_id: UUID | None = None


class NachtragAktualisieren(BaseModel):
    """Nachtrag-Felder aktualisieren."""
    gegenstand: str | None = Field(default=None, min_length=1, max_length=1000)
    beschreibung: str | None = None
    betrag_gefordert: float | None = None
    betrag_geprueft: float | None = None
    betrag_genehmigt: float | None = None
    zeitauswirkung_tage: int | None = None
    qualitaetsauswirkung: str | None = None
    nachtragsvariante: str | None = Field(default=None, pattern=r"^[ABC]$")
    lv_id: UUID | None = None
    kostengruppe_din276: str | None = Field(default=None, max_length=10)
    verantwortlich_firma_id: UUID | None = None


# ---------------------------------------------------------------------------
# Nachtrag Response
# ---------------------------------------------------------------------------

class NachtragResponse(BaseModel):
    """Nachtrag in Listen- und Detailansicht."""
    id: UUID
    nummer: str
    gegenstand: str
    beschreibung: str | None = None
    status: str
    prioritaet: str | None = None
    # Nachtrags-Felder
    betrag_gefordert: float | None = None
    betrag_geprueft: float | None = None
    betrag_genehmigt: float | None = None
    zeitauswirkung_tage: int | None = None
    nachtragsvariante: str | None = None
    qualitaetsauswirkung: str | None = None
    lv_id: UUID | None = None
    kostengruppe_din276: str | None = None
    ntv_id: UUID | None = None
    verantwortlich_firma_id: UUID | None = None
    # Audit
    erstellt_am: datetime
    erstellt_von: str | None = None
    geaendert_am: datetime | None = None


class NachtraegeListe(BaseModel):
    """Paginierte Nachtragsliste."""
    nachtraege: list[NachtragResponse]
    gesamt: int
    summe_gefordert: float | None = None
    summe_genehmigt: float | None = None


# ---------------------------------------------------------------------------
# Pruefschritt
# ---------------------------------------------------------------------------

class PruefschrittResponse(BaseModel):
    """Ein Schritt im 7-Schritte-Workflow."""
    id: UUID
    schritt: int
    titel: str
    ergebnis: str | None = None
    bearbeiter_id: UUID | None = None
    abgeschlossen: bool = False
    abgeschlossen_am: datetime | None = None
    # KI-Felder
    ki_eingabe: Any | None = None
    ki_ergebnis: Any | None = None
    ki_konfidenz: float | None = None
    ki_bestaetigt: bool | None = None
    ki_bestaetigt_von: UUID | None = None
    ki_bestaetigt_am: datetime | None = None
    # Audit
    erstellt_am: datetime
    erstellt_von: UUID


class PruefschrittAbschliessen(BaseModel):
    """Einen Pruefschritt abschliessen."""
    ergebnis: str = Field(min_length=1, max_length=10000)


class KiBestaetigung(BaseModel):
    """KI-Ergebnis bestaetigen oder ablehnen."""
    bestaetigt: bool
    kommentar: str | None = None


# ---------------------------------------------------------------------------
# Nachtrag mit Pruefschritten
# ---------------------------------------------------------------------------

class NachtragDetailResponse(NachtragResponse):
    """Nachtrag mit 7-Schritte-Workflow."""
    pruefschritte: list[PruefschrittResponse] = []
    aktueller_schritt: int = 0


# ---------------------------------------------------------------------------
# LV-Abgleich
# ---------------------------------------------------------------------------

class GenehmigterNT(BaseModel):
    """Bereits genehmigter Nachtrag an einer LV-Position.

    Wird je LVTreffer mitgegeben (NT-F-02 Doppelbeauftragungspruefung).
    Quelle: nachtragspruefung.ki_ergebnis.treffer[].lv_position_id mit
    Bestaetigungs-Gate (ki_bestaetigt=TRUE) und Vorgangsstatus 'genehmigt'.
    """
    vorgang_id: UUID
    nummer: str
    betrag_genehmigt: float | None = None
    status: str  # vorgangstatus-Enum als String


class LVTreffer(BaseModel):
    """Treffer beim LV-Abgleich.

    Das Feld bereits_genehmigte_nts (NT-F-02) listet alle anderen Nachtraege,
    die an genau dieser LV-Position bereits dem Grunde nach genehmigt wurden.
    Leere Liste = keine Doppelbeauftragungs-Gefahr.
    """
    lv_position_id: UUID
    oz: str
    kurztext: str
    einheit: str | None = None
    menge: float | None = None
    einheitspreis: float | None = None
    gesamtpreis: float | None = None
    lv_nummer: str | None = None
    relevanz: float = 0.0
    methode: str = "exakt"
    bereits_genehmigte_nts: list[GenehmigterNT] = []


class LVAbgleichResponse(BaseModel):
    """Ergebnis des LV-Abgleichs (Schritt 2)."""
    vorgang_id: UUID
    treffer: list[LVTreffer]
    anzahl_treffer: int = 0
    suchbegriff: str = ""


# ---------------------------------------------------------------------------
# Kostenabgleich
# ---------------------------------------------------------------------------

class KostenvergleichPosition(BaseModel):
    """Einzelner Preisvergleich."""
    quelle: str
    bezeichnung: str
    einheit: str | None = None
    referenzpreis_netto: float
    referenzpreis_regionalisiert: float | None = None
    abweichung_prozent: float | None = None
    bewertung: str = "unbekannt"


class KostenabgleichResponse(BaseModel):
    """Ergebnis des Kostenabgleichs (Schritt 3)."""
    vorgang_id: UUID
    betrag_gefordert: float | None = None
    vergleiche: list[KostenvergleichPosition]
    bki_regionalfaktor: float | None = None
    gesamtbewertung: str = "unbekannt"


# ---------------------------------------------------------------------------
# Entscheidungsvorlage
# ---------------------------------------------------------------------------

class EntscheidungsvorlageResponse(BaseModel):
    """Generierte Entscheidungsvorlage (Schritt 4)."""
    id: UUID
    vorgang_id: UUID
    version: int
    vorlage_text: str
    basisdaten: Any
    freigegeben: bool = False
    freigegeben_von: UUID | None = None
    freigegeben_am: datetime | None = None
    erstellt_am: datetime
    erstellt_von: UUID
    hinweis: str = "Entwurf — muss vor Verwendung freigegeben werden"


class VorlageFreigabe(BaseModel):
    """Vorlage freigeben (nur PL/Admin)."""
    kommentar: str | None = None
