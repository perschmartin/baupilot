"""Alembic env.py — Multi-Schema-Migration fuer BauPilot.

Entscheidung B-003: Schema-per-Tenant. Diese env.py stellt sicher,
dass Migrationen sowohl im shared-Schema als auch in jedem
tenant_*-Schema ausgefuehrt werden.

Alembic-Versionstabelle liegt im shared-Schema.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

# api/-Verzeichnis zum Pfad hinzufuegen, damit models importiert werden
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from models import Base  # noqa: E402

# Alembic Config
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata fuer Autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """Datenbank-URL aus Umgebungsvariable oder alembic.ini."""
    return os.environ.get(
        "DATABASE_URL",
        config.get_main_option("sqlalchemy.url", ""),
    )


def run_migrations_offline() -> None:
    """Migrationen im Offline-Modus (SQL-Ausgabe)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="shared",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migrationen im Online-Modus (direkt auf DB)."""
    connectable = create_engine(
        get_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Alembic-Versionstabelle im shared-Schema
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema="shared",
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
