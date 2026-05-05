"""BauPilot — Benutzer mit Rollen und Mandantenzuordnung.

Benutzer liegen im shared-Schema, Berechtigungen sind pro Projekt.
Authentifizierung: JWT + 2FA (TOTP).
"""

import enum

import uuid

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base


class BenutzerRolle(str, enum.Enum):
    ADMIN = "admin"
    PROJEKTLEITER = "projektleiter"
    OBJEKTUEBERWACHER = "objektueberwacher"
    FACHPLANER = "fachplaner"
    BAULEITER = "bauleiter"
    LESER = "leser"


class Benutzer(AuditMixin, Base):
    """Ein Benutzer der BauPilot-Plattform (shared-Schema)."""

    __tablename__ = "benutzer"
    __table_args__ = {"schema": "shared"}

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    passwort_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    vorname: Mapped[str] = mapped_column(String(127), nullable=False)
    nachname: Mapped[str] = mapped_column(String(127), nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_aktiviert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class BenutzerProjektRolle(AuditMixin, Base):
    """Zuordnung Benutzer → Projekt mit Rolle."""

    __tablename__ = "benutzer_projekt_rollen"
    __table_args__ = {"schema": "shared"}

    benutzer_id: Mapped["uuid.UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shared.benutzer.id"), nullable=False
    )
    mandant_slug: Mapped[str] = mapped_column(String(63), nullable=False)
    projekt_kurz: Mapped[str] = mapped_column(String(31), nullable=False)
    rolle: Mapped[BenutzerRolle] = mapped_column(
        SAEnum(BenutzerRolle, name="benutzerrolle"), nullable=False
    )


