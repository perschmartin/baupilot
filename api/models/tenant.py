"""BauPilot — Mandant (Tenant).

Liegt im shared-Schema. Verwaltet die Liste der Mandanten
und ordnet jedem Mandanten sein PostgreSQL-Schema zu.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base


class Mandant(AuditMixin, Base):
    """Ein Mandant (z.B. TLBV Thueringen).

    Jeder Mandant bekommt ein eigenes PostgreSQL-Schema
    (B-003: Schema-per-Tenant). Der slug wird zum Schema-Namen:
    tenant_{slug}.
    """

    __tablename__ = "mandanten"
    __table_args__ = {"schema": "shared"}

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    aktiv: Mapped[bool] = mapped_column(default=True, nullable=False)
