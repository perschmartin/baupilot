"""BauPilot — Vorgang (Nachtrag, Behinderung, Bedenken, Mangel, Aufgabe).

G3: Dreiklang als DNA — Q/Z/K Pflichtfelder an jedem Vorgang.
G8: Faktenbasierte Neutralitaet — keine Schuldzuweisungen.
B-002: Deterministische Kaskade mit vorgaenger_id + LLM-Vorschlagsschicht.
"""

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class VorgangTyp(str, enum.Enum):
    """Vorgangspraefix-Mapping."""

    NACHTRAG = "NT"
    BEHINDERUNG = "BA"
    BEDENKEN = "BK"
    MANGEL = "MA"
    AUFGABE = "AF"


class VorgangStatus(str, enum.Enum):
    OFFEN = "offen"
    IN_BEARBEITUNG = "in_bearbeitung"
    GEPRUEFT = "geprueft"
    BESTAETIGT = "bestaetigt"
    ABGELEHNT = "abgelehnt"
    ZURUECKGEWIESEN = "zurueckgewiesen"
    ABGESCHLOSSEN = "abgeschlossen"
    UEBERFAELLIG = "ueberfaellig"


class BeziehungsTyp(str, enum.Enum):
    """Typ der Verknuepfung zwischen Vorgaengen (B-002)."""

    LOEST_AUS = "loest_aus"
    WIDERSPRICHT = "widerspricht"
    ERSETZT = "ersetzt"
    GEHOERT_ZU = "gehoert_zu"
    FUEHRT_ZU = "fuehrt_zu"


class Vorgang(AuditMixin, Base):
    """Ein Vorgang im Bauprojekt.

    Traegt den Dreiklang Q/Z/K als Pflichtdimensionen (G3).
    Verknuepfung mit Vorgaenger ueber deterministische Kaskade (B-002).
    """

    __tablename__ = "vorgaenge"

    # Zuordnung
    projekt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id"), nullable=False
    )
    bauteil_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bauteile.id"), nullable=True
    )
    lv_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leistungsverzeichnisse.id"), nullable=True
    )

    # Identifikation
    typ: Mapped[VorgangTyp] = mapped_column(
        SAEnum(VorgangTyp, name="vorgangtyp"), nullable=False
    )
    nummer: Mapped[str] = mapped_column(String(31), nullable=False)
    gegenstand: Mapped[str] = mapped_column(String(500), nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[VorgangStatus] = mapped_column(
        SAEnum(VorgangStatus, name="vorgangstatus"),
        default=VorgangStatus.OFFEN,
        nullable=False,
    )

    # Dreiklang Q/Z/K (G3 — Pflichtdimensionen)
    kosten_eur: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    zeit_arbeitstage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualitaet_bewertung: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # Verantwortlichkeit (G8 — nur Fakten, keine Wertung)
    melder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verantwortlich: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- B-002: Deterministische Kaskade ---
    vorgaenger_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    beziehungstyp: Mapped[BeziehungsTyp | None] = mapped_column(
        SAEnum(BeziehungsTyp, name="beziehungstyp"), nullable=True
    )
    verknuepfung_erstellt_von: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    verknuepfung_konfidenz: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="1.0 bei menschlicher Verknuepfung, <1.0 bei LLM-Vorschlag",
    )

    # Beziehungen
    projekt: Mapped["Projekt"] = relationship(back_populates="vorgaenge")  # noqa: F821
    vorgaenger: Mapped["Vorgang | None"] = relationship(
        remote_side="Vorgang.id", foreign_keys=[vorgaenger_id]
    )
    dokumente: Mapped[list["Dokument"]] = relationship(  # noqa: F821
        back_populates="vorgang"
    )
    tags: Mapped[list["VorgangTag"]] = relationship(back_populates="vorgang")  # noqa: F821
