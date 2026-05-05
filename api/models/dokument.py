"""BauPilot — Dokument.

Jedes Dokument hat eine Klassifikationsstufe als Pflichtfeld.
VS-NfD-Dokumente bekommen separates Zugriffslog (B-006, noch offen).
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base
from models.lv import Klassifikation


class Dokument(AuditMixin, Base):
    """Ein Dokument, verknuepft mit einem Vorgang oder Projekt."""

    __tablename__ = "dokumente"

    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    projekt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id"), nullable=False
    )

    dateiname: Mapped[str] = mapped_column(String(500), nullable=False)
    dateipfad_minio: Mapped[str] = mapped_column(String(1000), nullable=False)
    dateityp: Mapped[str | None] = mapped_column(String(31), nullable=True)
    dateigroesse_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    klassifikation: Mapped[Klassifikation] = mapped_column(
        SAEnum(Klassifikation, name="klassifikation", create_type=False),
        default=Klassifikation.INTERN,
        nullable=False,
    )
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Beziehungen
    vorgang: Mapped["Vorgang | None"] = relationship(  # noqa: F821
        back_populates="dokumente"
    )
