"""BauPilot — Firma und Person.

FLI-Beteiligte: TLBV (Bauherr), BWP Architekten (GP),
AGE (GU, extern anonymisiert), Fachbueros (IBB, VA Heinekamp, Gerwert), FLI (Nutzer).
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class Firma(AuditMixin, Base):
    """Eine am Projekt beteiligte Firma."""

    __tablename__ = "firmen"

    projekt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kuerzel: Mapped[str | None] = mapped_column(String(15), nullable=True)
    rolle: Mapped[str | None] = mapped_column(String(127), nullable=True)
    adresse: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefon: Mapped[str | None] = mapped_column(String(63), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Beziehungen
    personen: Mapped[list["Person"]] = relationship(back_populates="firma")


class Person(AuditMixin, Base):
    """Eine Person innerhalb einer Firma."""

    __tablename__ = "personen"

    firma_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firmen.id"), nullable=False
    )
    vorname: Mapped[str] = mapped_column(String(127), nullable=False)
    nachname: Mapped[str] = mapped_column(String(127), nullable=False)
    rolle: Mapped[str | None] = mapped_column(String(127), nullable=True)
    telefon: Mapped[str | None] = mapped_column(String(63), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Beziehungen
    firma: Mapped["Firma"] = relationship(back_populates="personen")
