"""BauPilot — Tag-System.

Entscheidung B-001: Generisches Tag-System fuer Dimensionen,
die keine eigene Tabelle rechtfertigen (Bauphase, Brandabschnitt, etc.).
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class Tag(AuditMixin, Base):
    """Ein Tag (z.B. Kategorie=Bauphase, Wert=Rohbau)."""

    __tablename__ = "tags"

    projekt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id"), nullable=False
    )
    kategorie: Mapped[str] = mapped_column(String(63), nullable=False)
    wert: Mapped[str] = mapped_column(String(127), nullable=False)

    __table_args__ = (
        UniqueConstraint("projekt_id", "kategorie", "wert", name="uq_tag_projekt"),
    )


class VorgangTag(AuditMixin, Base):
    """Zuordnung Vorgang → Tag (m:n)."""

    __tablename__ = "vorgang_tags"

    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=False
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id"), nullable=False
    )

    # Beziehungen
    vorgang: Mapped["Vorgang"] = relationship(back_populates="tags")  # noqa: F821
    tag: Mapped["Tag"] = relationship()

    __table_args__ = (
        UniqueConstraint("vorgang_id", "tag_id", name="uq_vorgang_tag"),
    )
