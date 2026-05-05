"""BauPilot — SQLAlchemy-Basisklasse mit Audit-Feldern.

G2: Revisionssicherheit — jeder Eintrag mit Zeitstempel, Urheber,
nicht-loeschbarer Historie. Rechnungshof-tauglich ab Tag 1.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Abstrakte Basisklasse fuer alle BauPilot-Modelle."""

    pass


class AuditMixin:
    """Audit-Felder an jeder Tabelle (G2 Revisionssicherheit).

    Soft-Delete statt hartem Loeschen — Eintraege werden als geloescht
    markiert, aber nie physisch entfernt.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    erstellt_von: Mapped[str] = mapped_column(
        String(255), nullable=False, default="system"
    )
    geaendert_am: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc)
    )
    geaendert_von: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geloescht: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    geloescht_am: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    geloescht_von: Mapped[str | None] = mapped_column(String(255), nullable=True)
