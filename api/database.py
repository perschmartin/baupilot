"""BauPilot — Datenbankverbindung und Schema-per-Tenant-Logik.

Entscheidung B-003: Schema-per-Tenant.
Jeder Mandant bekommt ein eigenes PostgreSQL-Schema (z.B. tenant_tlbv).
Pro Request wird SET LOCAL search_path gesetzt.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=(settings.environment == "development"),
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# --- Schema-per-Tenant ---

SHARED_SCHEMA = "shared"
TENANT_SCHEMA_PREFIX = "tenant_"


def tenant_schema_name(tenant_slug: str) -> str:
    """Erzeugt den Schema-Namen fuer einen Mandanten."""
    return f"{TENANT_SCHEMA_PREFIX}{tenant_slug}"


@contextmanager
def tenant_session(tenant_slug: str) -> Generator[Session, None, None]:
    """Oeffnet eine DB-Session mit search_path auf das Mandanten-Schema.

    Verwendet SET LOCAL, damit der search_path nur innerhalb der
    aktuellen Transaktion gilt — keine Connection-Pool-Bugs (B-003).
    """
    session = SessionLocal()
    try:
        schema = tenant_schema_name(tenant_slug)
        session.execute(
            text(f"SET LOCAL search_path TO {schema}, {SHARED_SCHEMA}, public")
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """Einfache Session ohne Tenant-Kontext (fuer Health-Checks etc.)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_tenant_schema(tenant_slug: str) -> None:
    """Legt ein neues Mandanten-Schema an und fuehrt Migrationen aus."""
    schema = tenant_schema_name(tenant_slug)
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        conn.commit()


def create_shared_schema() -> None:
    """Legt das gemeinsame Schema an (Mandanten-Verzeichnis, Benutzer)."""
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SHARED_SCHEMA}"))
        conn.commit()
