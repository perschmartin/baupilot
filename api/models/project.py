"""BauPilot — Projekt.

Ein Projekt innerhalb eines Mandanten (z.B. FLI Jena).
G10: Mandantenfaehigkeit — jeder Datensatz gehoert zu einem Projekt.
"""

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base

import enum


class ProjektStatus(str, enum.Enum):
    PLANUNG = "planung"
    BAU = "bau"
    ABNAHME = "abnahme"
    GEWAEHRLEISTUNG = "gewaehrleistung"
    ABGESCHLOSSEN = "abgeschlossen"


class Projekt(AuditMixin, Base):
    """Ein Bauprojekt innerhalb eines Mandanten-Schemas."""

    __tablename__ = "projekte"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kurz: Mapped[str] = mapped_column(String(31), nullable=False, unique=True)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjektStatus] = mapped_column(
        SAEnum(ProjektStatus, name="projektstatus"),
        default=ProjektStatus.BAU,
        nullable=False,
    )
    standort: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Beziehungen (String-Referenzen vermeiden zirkulaere Imports)
    bauteile: Mapped[list["Bauteil"]] = relationship(  # noqa: F821
        back_populates="projekt"
    )
    leistungsverzeichnisse: Mapped[list["Leistungsverzeichnis"]] = relationship(  # noqa: F821
        back_populates="projekt"
    )
    vorgaenge: Mapped[list["Vorgang"]] = relationship(  # noqa: F821
        back_populates="projekt"
    )
