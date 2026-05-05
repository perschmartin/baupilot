"""BauPilot — Leistungsverzeichnis (LV) und LV-Position.

LV-Nummernkreise FLI: 100er = GU-Gewerke, 200er = TGA,
300er = Laborausstattung, 400er = Aussenanlagen, 500er = Zusatzleistungen.
"""

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class Klassifikation(str, enum.Enum):
    """Klassifikationsstufen fuer Dokumente und LVs."""

    OFFEN = "offen"
    INTERN = "intern"
    VERTRAULICH = "vertraulich"
    VS_NFD = "vs_nfd"
    VS_VERTRAULICH = "vs_vertraulich"
    VS_GEHEIM = "vs_geheim"
    VS_STRENG_GEHEIM = "vs_streng_geheim"


class Leistungsverzeichnis(AuditMixin, Base):
    """Ein Leistungsverzeichnis (z.B. LV 211, LV 330)."""

    __tablename__ = "leistungsverzeichnisse"

    projekt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id"), nullable=False
    )
    bauteil_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bauteile.id"), nullable=True
    )
    nummer: Mapped[str] = mapped_column(String(31), nullable=False)
    bezeichnung: Mapped[str] = mapped_column(String(500), nullable=False)
    nummernkreis: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gewerk: Mapped[str | None] = mapped_column(String(15), nullable=True)
    klassifikation: Mapped[Klassifikation] = mapped_column(
        SAEnum(Klassifikation, name="klassifikation"),
        default=Klassifikation.INTERN,
        nullable=False,
    )

    # Beziehungen
    projekt: Mapped["Projekt"] = relationship(  # noqa: F821
        back_populates="leistungsverzeichnisse"
    )
    positionen: Mapped[list["LVPosition"]] = relationship(back_populates="lv")


class LVPosition(AuditMixin, Base):
    """Eine einzelne Position im Leistungsverzeichnis (OZ, Menge, EP, GP)."""

    __tablename__ = "lv_positionen"

    lv_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leistungsverzeichnisse.id"), nullable=False
    )
    oz: Mapped[str] = mapped_column(String(63), nullable=False)
    kurztext: Mapped[str] = mapped_column(String(500), nullable=False)
    langtext: Mapped[str | None] = mapped_column(Text, nullable=True)
    einheit: Mapped[str | None] = mapped_column(String(31), nullable=True)
    menge: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    einheitspreis: Mapped[float | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    gesamtpreis: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )

    # Beziehungen
    lv: Mapped["Leistungsverzeichnis"] = relationship(back_populates="positionen")
