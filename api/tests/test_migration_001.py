"""Tests fuer Migration 001 — Initiales Datenbankschema.

Prueft, dass alle Tabellen und kritische Spalten nach der Migration
in den richtigen Schemata existieren.

Voraussetzung: Migration 001 wurde bereits ausgefuehrt.
"""

import os

import pytest
from sqlalchemy import create_engine, inspect, text


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://{user}:{pw}@{host}:{port}/{db}".format(
        user=os.environ.get("POSTGRES_USER", "baupilot"),
        pw=os.environ.get("POSTGRES_PASSWORD", "baupilot_dev"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5436"),
        db=os.environ.get("POSTGRES_DB", "baupilot"),
    )
)

# --- Erwartete Struktur ---------------------------------------------------

SHARED_TABLES = {"mandanten", "benutzer", "benutzer_projekt_rollen"}

TENANT_TABLES = {
    "projekte", "bauteile", "leistungsverzeichnisse", "lv_positionen",
    "vorgaenge", "dokumente", "firmen", "personen", "tags", "vorgang_tags",
}

# Kritische Spalten pro Tabelle (nicht alle, aber die entscheidungsrelevanten)
CRITICAL_COLUMNS = {
    # Shared
    ("shared", "mandanten"): {"id", "name", "slug", "aktiv"},
    ("shared", "benutzer"): {"id", "email", "passwort_hash", "totp_aktiviert"},
    ("shared", "benutzer_projekt_rollen"): {"id", "benutzer_id", "mandant_slug", "rolle"},
    # Tenant — B-001 Bauteil-Ebene
    ("tenant", "bauteile"): {"id", "projekt_id", "kennung", "typ"},
    # Tenant — B-002 Verknuepfungsanalyse
    ("tenant", "vorgaenge"): {
        "id", "projekt_id", "typ", "nummer", "status",
        "kosten_eur", "zeit_arbeitstage", "qualitaet_bewertung",  # Dreiklang
        "vorgaenger_id", "beziehungstyp", "konfidenz",  # B-002
        "konfidenz_bestaetigt",  # B-002 Bestaetigungs-Gate
        "bauteil_id", "lv_id",  # B-001 optionale FKs
    },
    # Tenant — Dokumente mit Klassifikation
    ("tenant", "dokumente"): {"id", "klassifikation", "dateipfad_minio", "version"},
    # Tenant — Tag-System (B-001)
    ("tenant", "tags"): {"id", "projekt_id", "kategorie", "wert"},
    ("tenant", "vorgang_tags"): {"id", "vorgang_id", "tag_id"},
    # Tenant — LV
    ("tenant", "leistungsverzeichnisse"): {"id", "projekt_id", "nummer", "bauteil_id", "klassifikation"},
    ("tenant", "lv_positionen"): {"id", "lv_id", "oz", "menge", "einheitspreis", "gesamtpreis"},
}

# Audit-Spalten, die an jeder Tabelle haengen muessen (G2)
AUDIT_COLUMNS = {
    "id", "erstellt_am", "erstellt_von", "geaendert_am",
    "geaendert_von", "geloescht", "geloescht_am", "geloescht_von",
}


# --- Fixtures --------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    return create_engine(DATABASE_URL)


@pytest.fixture(scope="module")
def inspector(engine):
    return inspect(engine)


@pytest.fixture(scope="module")
def tenant_schemas(engine):
    """Alle tenant_*-Schemata aus der Datenbank lesen."""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'tenant_%' ORDER BY schema_name"
        ))
        schemas = [row[0] for row in result]
    assert len(schemas) > 0, "Kein Tenant-Schema gefunden. init-db.ps1 gelaufen?"
    return schemas


# --- Tests -----------------------------------------------------------------

class TestSharedSchema:
    """Prueft das shared-Schema."""

    def test_shared_schema_exists(self, inspector):
        schemas = inspector.get_schema_names()
        assert "shared" in schemas, "Schema 'shared' fehlt"

    def test_shared_tables_exist(self, inspector):
        tables = set(inspector.get_table_names(schema="shared"))
        missing = SHARED_TABLES - tables
        assert not missing, f"Fehlende Tabellen im shared-Schema: {missing}"

    @pytest.mark.parametrize("table", sorted(SHARED_TABLES))
    def test_shared_audit_columns(self, inspector, table):
        columns = {c["name"] for c in inspector.get_columns(table, schema="shared")}
        missing = AUDIT_COLUMNS - columns
        assert not missing, f"shared.{table}: Audit-Spalten fehlen: {missing}"

    @pytest.mark.parametrize("key", [
        k for k in CRITICAL_COLUMNS if k[0] == "shared"
    ])
    def test_shared_critical_columns(self, inspector, key):
        schema, table = key
        columns = {c["name"] for c in inspector.get_columns(table, schema=schema)}
        expected = CRITICAL_COLUMNS[key]
        missing = expected - columns
        assert not missing, f"{schema}.{table}: Spalten fehlen: {missing}"


class TestTenantSchema:
    """Prueft die Tenant-Schemata."""

    def test_tenant_schemas_exist(self, tenant_schemas):
        assert "tenant_tlbv" in tenant_schemas, "Schema 'tenant_tlbv' fehlt"

    def test_tenant_tables_exist(self, inspector, tenant_schemas):
        for schema in tenant_schemas:
            tables = set(inspector.get_table_names(schema=schema))
            missing = TENANT_TABLES - tables
            assert not missing, f"Fehlende Tabellen in {schema}: {missing}"

    @pytest.mark.parametrize("table", sorted(TENANT_TABLES))
    def test_tenant_audit_columns(self, inspector, tenant_schemas, table):
        for schema in tenant_schemas:
            columns = {c["name"] for c in inspector.get_columns(table, schema=schema)}
            missing = AUDIT_COLUMNS - columns
            assert not missing, f"{schema}.{table}: Audit-Spalten fehlen: {missing}"

    @pytest.mark.parametrize("key", [
        k for k in CRITICAL_COLUMNS if k[0] == "tenant"
    ])
    def test_tenant_critical_columns(self, inspector, tenant_schemas, key):
        _, table = key
        expected = CRITICAL_COLUMNS[key]
        for schema in tenant_schemas:
            columns = {c["name"] for c in inspector.get_columns(table, schema=schema)}
            missing = expected - columns
            assert not missing, f"{schema}.{table}: Spalten fehlen: {missing}"


class TestEnumTypes:
    """Prueft, dass alle Enum-Typen angelegt wurden."""

    EXPECTED_ENUMS = {
        "projektstatus", "bauteiltyp", "klassifikation",
        "vorgangtyp", "vorgangstatus", "beziehungstyp", "benutzerrolle",
    }

    def test_enum_types_exist(self, engine):
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname"
            ))
            enums = {row[0] for row in result}

        missing = self.EXPECTED_ENUMS - enums
        assert not missing, f"Fehlende Enum-Typen: {missing}"


class TestAlembicVersion:
    """Prueft, dass Alembic die Revision 001 registriert hat."""

    def test_alembic_version_is_001(self, engine):
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT version_num FROM shared.alembic_version"
            ))
            versions = [row[0] for row in result]

        # Mindestens eine Version muss vorhanden sein (Migration wurde ausgefuehrt)
        assert len(versions) > 0, f"Keine Alembic-Version gefunden"


class TestDecisionCompliance:
    """Prueft die Umsetzung der Architekturentscheidungen B-001 bis B-003."""

    def test_b001_bauteil_optional_fk_on_vorgang(self, inspector, tenant_schemas):
        """B-001: bauteil_id an vorgaenge muss nullable sein."""
        for schema in tenant_schemas:
            cols = {c["name"]: c for c in inspector.get_columns("vorgaenge", schema=schema)}
            assert cols["bauteil_id"]["nullable"], \
                f"{schema}.vorgaenge.bauteil_id muss nullable sein (B-001)"

    def test_b001_bauteil_optional_fk_on_lv(self, inspector, tenant_schemas):
        """B-001: bauteil_id an leistungsverzeichnisse muss nullable sein."""
        for schema in tenant_schemas:
            cols = {c["name"]: c for c in inspector.get_columns("leistungsverzeichnisse", schema=schema)}
            assert cols["bauteil_id"]["nullable"], \
                f"{schema}.leistungsverzeichnisse.bauteil_id muss nullable sein (B-001)"

    def test_b001_tag_system_exists(self, inspector, tenant_schemas):
        """B-001: Tag-System mit tags + vorgang_tags Tabellen."""
        for schema in tenant_schemas:
            tables = set(inspector.get_table_names(schema=schema))
            assert "tags" in tables, f"{schema}: Tabelle 'tags' fehlt (B-001)"
            assert "vorgang_tags" in tables, f"{schema}: Tabelle 'vorgang_tags' fehlt (B-001)"

    def test_b002_verknuepfung_columns(self, inspector, tenant_schemas):
        """B-002: vorgaenger_id, beziehungstyp, konfidenz an vorgaenge."""
        required = {"vorgaenger_id", "beziehungstyp", "konfidenz", "konfidenz_bestaetigt"}
        for schema in tenant_schemas:
            cols = {c["name"] for c in inspector.get_columns("vorgaenge", schema=schema)}
            missing = required - cols
            assert not missing, f"{schema}.vorgaenge: B-002-Spalten fehlen: {missing}"

    def test_b003_shared_and_tenant_separation(self, inspector, tenant_schemas):
        """B-003: mandanten + benutzer in shared, projekte in tenant_*."""
        shared_tables = set(inspector.get_table_names(schema="shared"))
        assert "mandanten" in shared_tables
        assert "benutzer" in shared_tables
        assert "projekte" not in shared_tables, "projekte darf nicht in shared sein"

        for schema in tenant_schemas:
            tenant_tables = set(inspector.get_table_names(schema=schema))
            assert "projekte" in tenant_tables
            assert "mandanten" not in tenant_tables, \
                f"mandanten darf nicht in {schema} sein"

    def test_g2_audit_on_all_tables(self, inspector, tenant_schemas):
        """G2: Jede Tabelle hat Audit-Spalten."""
        all_checks = []

        for table in SHARED_TABLES:
            cols = {c["name"] for c in inspector.get_columns(table, schema="shared")}
            missing = AUDIT_COLUMNS - cols
            if missing:
                all_checks.append(f"shared.{table}: {missing}")

        for schema in tenant_schemas:
            for table in TENANT_TABLES:
                cols = {c["name"] for c in inspector.get_columns(table, schema=schema)}
                missing = AUDIT_COLUMNS - cols
                if missing:
                    all_checks.append(f"{schema}.{table}: {missing}")

        assert not all_checks, f"G2-Verletzung — Audit-Spalten fehlen:\n" + "\n".join(all_checks)

    def test_g3_dreiklang_on_vorgaenge(self, inspector, tenant_schemas):
        """G3: Dreiklang Q/Z/K als Pflichtfelder an vorgaenge."""
        dreiklang = {"kosten_eur", "zeit_arbeitstage", "qualitaet_bewertung"}
        for schema in tenant_schemas:
            cols = {c["name"] for c in inspector.get_columns("vorgaenge", schema=schema)}
            missing = dreiklang - cols
            assert not missing, f"{schema}.vorgaenge: Dreiklang-Spalten fehlen: {missing}"
