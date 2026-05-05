"""BauPilot — Bauteil / Gebaeudeabschnitt.

Entscheidung B-001: Bauteil-Ebene mit optionalem FK.
FLI-Kontext: Geb. 30, 31, 32, 33, 34, Aussenanlagen.
Die Bauteil-Referenz an Vorgaengen und LVs ist optional (NULL erlaubt).
"""

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

import uuid

from models.base import AuditMixin, Base


class BauteilTyp(str, enum.Enum):
    GEBAEUDEABSCHNITT = "gebaeudeabschnitt"
    AUSSENANLAGE = "aussenanlage"
    SONSTIGES = "sonstiges"


class Bauteil(AuditMixin, Base):
    """Ein Bauteil / Gebaeudeabschnitt innerhalb eines Projekts.

    B-001 Synthese: Die UI zeigt die Bauteil-Ebene nur an,
    wenn im Projekt mehr als ein Bauteil existiert.
    """

    __tablename__ = "bauteile"

    projekt_id: Mapped["uuid.UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id"), nullable=False
    )
    kennung: Mapped[str] = mapped_column(String(31), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    typ: Mapped[BauteilTyp] = mapped_column(
        SAEnum(BauteilTyp, name="bauteiltyp"),
        default=BauteilTyp.GEBAEUDEABSCHNITT,
        nullable=False,
    )
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Beziehungen
    projekt: Mapped["Projekt"] = relationship(back_populates="bauteile")  # noqa: F821


