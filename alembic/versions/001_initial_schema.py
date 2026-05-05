"""001 — Initiales BauPilot-Datenbankschema.

Erstellt alle Tabellen gemaess Datenmodell BP-V-01 und
Entscheidungen B-001 (Bauteil-Ebene), B-002 (Verknuepfungsanalyse),
B-003 (Schema-per-Tenant), B-004 (Stack).

Shared-Schema:  mandanten, benutzer, benutzer_projekt_rollen
Tenant-Schema:  projekte, bauteile, leistungsverzeichnisse, lv_positionen,
                vorgaenge, dokumente, firmen, personen, tags, vorgang_tags

Revision ID: 001
Revises: —
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# Revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


# --- Enum-Typen -----------------------------------------------------------

projektstatus = sa.Enum(
    "aktiv", "abgeschlossen", "archiviert", "pausiert",
    name="projektstatus",
)

bauteiltyp = sa.Enum(
    "gebaeudeabschnitt", "brandabschnitt", "aussenanlage", "sonstiges",
    name="bauteiltyp",
)

klassifikation = sa.Enum(
    "offen", "intern", "vertraulich", "vs_nfd",
    "vs_vertraulich", "vs_geheim", "vs_streng_geheim",
    name="klassifikation",
)

vorgangtyp = sa.Enum(
    "nachtrag", "behinderungsanzeige", "bedenkenanzeige",
    "mangelanzeige", "aufgabe",
    name="vorgangtyp",
)

vorgangstatus = sa.Enum(
    "offen", "in_bearbeitung", "geprueft", "genehmigt",
    "abgelehnt", "abgeschlossen", "storniert",
    name="vorgangstatus",
)

beziehungstyp = sa.Enum(
    "loest_aus", "widerspricht", "ersetzt", "konkretisiert",
    "gehoert_zu", "llm_vorschlag",
    name="beziehungstyp",
)

benutzerrolle = sa.Enum(
    "admin", "projektleiter", "objektueberwacher",
    "fachplaner", "bauleiter", "leser",
    name="benutzerrolle",
)


# --- Audit-Spalten (G2 Revisionssicherheit) --------------------------------

def _audit_columns():
    """Gibt die Standard-Audit-Spalten zurueck, die an jeder Tabelle haengen."""
    return [
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("erstellt_am", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("erstellt_von", sa.String(255), nullable=False,
                  server_default="system"),
        sa.Column("geaendert_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geaendert_von", sa.String(255), nullable=True),
        sa.Column("geloescht", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("geloescht_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geloescht_von", sa.String(255), nullable=True),
    ]


# ===========================================================================
# SHARED-SCHEMA
# ===========================================================================

def _create_shared_tables():
    """Tabellen im shared-Schema: mandanten, benutzer, benutzer_projekt_rollen."""

    # --- mandanten ---------------------------------------------------------
    op.create_table(
        "mandanten",
        *_audit_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.UniqueConstraint("slug", name="uq_mandanten_slug"),
        schema="shared",
    )

    # --- benutzer ----------------------------------------------------------
    op.create_table(
        "benutzer",
        *_audit_columns(),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("passwort_hash", sa.String(500), nullable=False),
        sa.Column("vorname", sa.String(127), nullable=False),
        sa.Column("nachname", sa.String(127), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("totp_secret", sa.String(255), nullable=True),
        sa.Column("totp_aktiviert", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.UniqueConstraint("email", name="uq_benutzer_email"),
        schema="shared",
    )

    # --- benutzer_projekt_rollen -------------------------------------------
    op.create_table(
        "benutzer_projekt_rollen",
        *_audit_columns(),
        sa.Column("benutzer_id", UUID(as_uuid=True),
                  sa.ForeignKey("shared.benutzer.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("mandant_slug", sa.String(63), nullable=False),
        sa.Column("projekt_kurz", sa.String(31), nullable=False),
        sa.Column("rolle", benutzerrolle, nullable=False),
        sa.Index("ix_bpr_benutzer", "benutzer_id"),
        sa.Index("ix_bpr_mandant_projekt", "mandant_slug", "projekt_kurz"),
        schema="shared",
    )


def _drop_shared_tables():
    """Shared-Tabellen entfernen (Downgrade)."""
    op.drop_table("benutzer_projekt_rollen", schema="shared")
    op.drop_table("benutzer", schema="shared")
    op.drop_table("mandanten", schema="shared")


# ===========================================================================
# TENANT-SCHEMA (wird pro Mandant aufgerufen)
# ===========================================================================

def _create_tenant_tables(schema: str):
    """Alle projektbezogenen Tabellen in einem Mandanten-Schema anlegen."""

    # --- Enums im Tenant-Schema erstellen ----------------------------------
    # Enums sind datenbankweit, nicht schema-spezifisch. Wir erstellen sie
    # nur einmal (beim ersten Tenant). create_type=False verhindert Fehler
    # bei weiteren Tenants.

    # --- projekte ----------------------------------------------------------
    op.create_table(
        "projekte",
        *_audit_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kurz", sa.String(31), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("status", projektstatus, nullable=False,
                  server_default="aktiv"),
        sa.Column("auftraggeber", sa.String(255), nullable=True),
        sa.Column("ort", sa.String(255), nullable=True),
        sa.Column("baubeginn", sa.Date(), nullable=True),
        sa.Column("bauende_soll", sa.Date(), nullable=True),
        sa.Column("bauende_ist", sa.Date(), nullable=True),
        sa.Column("gesamtkosten_eur", sa.Numeric(14, 2), nullable=True),
        sa.UniqueConstraint("kurz", name=f"uq_{schema}_projekte_kurz"),
        schema=schema,
    )

    # --- bauteile (B-001: eigene Tabelle, optionaler FK) -------------------
    op.create_table(
        "bauteile",
        *_audit_columns(),
        sa.Column("projekt_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.projekte.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("kennung", sa.String(31), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("typ", bauteiltyp, nullable=False,
                  server_default="gebaeudeabschnitt"),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.UniqueConstraint("projekt_id", "kennung",
                            name=f"uq_{schema}_bauteile_kennung"),
        sa.Index(f"ix_{schema}_bauteile_projekt", "projekt_id"),
        schema=schema,
    )

    # --- leistungsverzeichnisse --------------------------------------------
    op.create_table(
        "leistungsverzeichnisse",
        *_audit_columns(),
        sa.Column("projekt_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.projekte.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("bauteil_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.bauteile.id", ondelete="SET NULL"),
                  nullable=True),  # B-001: optionaler FK
        sa.Column("nummer", sa.String(31), nullable=False),
        sa.Column("bezeichnung", sa.String(500), nullable=False),
        sa.Column("nummernkreis", sa.SmallInteger(), nullable=True),
        sa.Column("klassifikation", klassifikation, nullable=False,
                  server_default="intern"),
        sa.Column("vertragsdatum", sa.Date(), nullable=True),
        sa.Column("auftragnehmer", sa.String(255), nullable=True),
        sa.UniqueConstraint("projekt_id", "nummer",
                            name=f"uq_{schema}_lv_nummer"),
        sa.Index(f"ix_{schema}_lv_projekt", "projekt_id"),
        sa.Index(f"ix_{schema}_lv_bauteil", "bauteil_id"),
        sa.Index(f"ix_{schema}_lv_nummernkreis", "nummernkreis"),
        schema=schema,
    )

    # --- lv_positionen -----------------------------------------------------
    op.create_table(
        "lv_positionen",
        *_audit_columns(),
        sa.Column("lv_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.leistungsverzeichnisse.id",
                                ondelete="CASCADE"),
                  nullable=False),
        sa.Column("oz", sa.String(31), nullable=False),
        sa.Column("kurztext", sa.String(1000), nullable=False),
        sa.Column("langtext", sa.Text(), nullable=True),
        sa.Column("einheit", sa.String(31), nullable=True),
        sa.Column("menge", sa.Numeric(14, 4), nullable=True),
        sa.Column("einheitspreis", sa.Numeric(14, 4), nullable=True),
        sa.Column("gesamtpreis", sa.Numeric(14, 2), nullable=True),
        sa.UniqueConstraint("lv_id", "oz",
                            name=f"uq_{schema}_lvpos_oz"),
        sa.Index(f"ix_{schema}_lvpos_lv", "lv_id"),
        schema=schema,
    )

    # --- firmen ------------------------------------------------------------
    op.create_table(
        "firmen",
        *_audit_columns(),
        sa.Column("projekt_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.projekte.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kuerzel", sa.String(15), nullable=True),
        sa.Column("rolle", sa.String(127), nullable=True),
        sa.Column("adresse", sa.Text(), nullable=True),
        sa.Column("telefon", sa.String(63), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Index(f"ix_{schema}_firmen_projekt", "projekt_id"),
        schema=schema,
    )

    # --- personen ----------------------------------------------------------
    op.create_table(
        "personen",
        *_audit_columns(),
        sa.Column("firma_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.firmen.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("vorname", sa.String(127), nullable=False),
        sa.Column("nachname", sa.String(127), nullable=False),
        sa.Column("rolle", sa.String(127), nullable=True),
        sa.Column("telefon", sa.String(63), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Index(f"ix_{schema}_personen_firma", "firma_id"),
        schema=schema,
    )

    # --- vorgaenge (Nachtrag, BA, BK, Mangel, Aufgabe) --------------------
    op.create_table(
        "vorgaenge",
        *_audit_columns(),
        sa.Column("projekt_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.projekte.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("bauteil_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.bauteile.id", ondelete="SET NULL"),
                  nullable=True),  # B-001: optionaler FK
        sa.Column("lv_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.leistungsverzeichnisse.id",
                                ondelete="SET NULL"),
                  nullable=True),
        sa.Column("typ", vorgangtyp, nullable=False),
        sa.Column("nummer", sa.String(31), nullable=False),
        sa.Column("gegenstand", sa.String(1000), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("status", vorgangstatus, nullable=False,
                  server_default="offen"),
        # --- Dreiklang Q/Z/K (G3) ---
        sa.Column("kosten_eur", sa.Numeric(14, 2), nullable=True),
        sa.Column("zeit_arbeitstage", sa.Integer(), nullable=True),
        sa.Column("qualitaet_bewertung", sa.String(500), nullable=True),
        # --- Verknuepfung (B-002: deterministisch + LLM-Konfidenz) ---
        sa.Column("vorgaenger_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.vorgaenge.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("beziehungstyp", beziehungstyp, nullable=True),
        sa.Column("konfidenz", sa.Float(), nullable=True),
        sa.Column("konfidenz_bestaetigt", sa.Boolean(), nullable=True),
        sa.Column("konfidenz_bestaetigt_von", sa.String(255), nullable=True),
        sa.Column("konfidenz_bestaetigt_am", sa.DateTime(timezone=True),
                  nullable=True),
        # --- Verantwortlichkeit ---
        sa.Column("verantwortlich_firma_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.firmen.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("frist", sa.Date(), nullable=True),
        sa.UniqueConstraint("projekt_id", "typ", "nummer",
                            name=f"uq_{schema}_vorgaenge_nummer"),
        sa.Index(f"ix_{schema}_vorgaenge_projekt", "projekt_id"),
        sa.Index(f"ix_{schema}_vorgaenge_typ", "typ"),
        sa.Index(f"ix_{schema}_vorgaenge_status", "status"),
        sa.Index(f"ix_{schema}_vorgaenge_bauteil", "bauteil_id"),
        sa.Index(f"ix_{schema}_vorgaenge_lv", "lv_id"),
        sa.Index(f"ix_{schema}_vorgaenge_vorgaenger", "vorgaenger_id"),
        sa.Index(f"ix_{schema}_vorgaenge_frist", "frist"),
        schema=schema,
    )

    # --- dokumente ---------------------------------------------------------
    op.create_table(
        "dokumente",
        *_audit_columns(),
        sa.Column("projekt_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.projekte.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("vorgang_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.vorgaenge.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("dateiname", sa.String(500), nullable=False),
        sa.Column("dateipfad_minio", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=True),
        sa.Column("groesse_bytes", sa.BigInteger(), nullable=True),
        sa.Column("klassifikation", klassifikation, nullable=False,
                  server_default="intern"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pruefsumme_sha256", sa.String(64), nullable=True),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Index(f"ix_{schema}_dokumente_projekt", "projekt_id"),
        sa.Index(f"ix_{schema}_dokumente_vorgang", "vorgang_id"),
        sa.Index(f"ix_{schema}_dokumente_klassifikation", "klassifikation"),
        schema=schema,
    )

    # --- tags (B-001: Tag-System fuer flexible Dimensionen) ----------------
    op.create_table(
        "tags",
        *_audit_columns(),
        sa.Column("projekt_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.projekte.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("kategorie", sa.String(63), nullable=False),
        sa.Column("wert", sa.String(255), nullable=False),
        sa.UniqueConstraint("projekt_id", "kategorie", "wert",
                            name=f"uq_{schema}_tags_kat_wert"),
        sa.Index(f"ix_{schema}_tags_projekt", "projekt_id"),
        sa.Index(f"ix_{schema}_tags_kategorie", "kategorie"),
        schema=schema,
    )

    # --- vorgang_tags (Zuordnung Vorgang ↔ Tag) ----------------------------
    op.create_table(
        "vorgang_tags",
        *_audit_columns(),
        sa.Column("vorgang_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.vorgaenge.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("tag_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{schema}.tags.id", ondelete="CASCADE"),
                  nullable=False),
        sa.UniqueConstraint("vorgang_id", "tag_id",
                            name=f"uq_{schema}_vorgang_tags"),
        sa.Index(f"ix_{schema}_vorgang_tags_vorgang", "vorgang_id"),
        sa.Index(f"ix_{schema}_vorgang_tags_tag", "tag_id"),
        schema=schema,
    )


def _drop_tenant_tables(schema: str):
    """Alle Tenant-Tabellen entfernen (Downgrade)."""
    for table in [
        "vorgang_tags", "tags", "dokumente", "vorgaenge",
        "personen", "firmen", "lv_positionen", "leistungsverzeichnisse",
        "bauteile", "projekte",
    ]:
        op.drop_table(table, schema=schema)


# ===========================================================================
# Hilfsfunktion: Alle Tenant-Schemata ermitteln
# ===========================================================================

def _get_tenant_schemas():
    """Liest alle Schemata, die mit 'tenant_' beginnen, aus der Datenbank."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'tenant_%' ORDER BY schema_name"
        )
    )
    return [row[0] for row in result]


# ===========================================================================
# UPGRADE / DOWNGRADE
# ===========================================================================

def upgrade():
    # 1. Enum-Typen erstellen (datenbankweit, nicht schema-gebunden)
    projektstatus.create(op.get_bind(), checkfirst=True)
    bauteiltyp.create(op.get_bind(), checkfirst=True)
    klassifikation.create(op.get_bind(), checkfirst=True)
    vorgangtyp.create(op.get_bind(), checkfirst=True)
    vorgangstatus.create(op.get_bind(), checkfirst=True)
    beziehungstyp.create(op.get_bind(), checkfirst=True)
    benutzerrolle.create(op.get_bind(), checkfirst=True)

    # 2. Shared-Tabellen
    _create_shared_tables()

    # 3. Tenant-Tabellen fuer jedes existierende Tenant-Schema
    for schema in _get_tenant_schemas():
        _create_tenant_tables(schema)


def downgrade():
    # 1. Tenant-Tabellen entfernen
    for schema in _get_tenant_schemas():
        _drop_tenant_tables(schema)

    # 2. Shared-Tabellen entfernen
    _drop_shared_tables()

    # 3. Enum-Typen entfernen
    benutzerrolle.drop(op.get_bind(), checkfirst=True)
    beziehungstyp.drop(op.get_bind(), checkfirst=True)
    vorgangstatus.drop(op.get_bind(), checkfirst=True)
    vorgangtyp.drop(op.get_bind(), checkfirst=True)
    klassifikation.drop(op.get_bind(), checkfirst=True)
    bauteiltyp.drop(op.get_bind(), checkfirst=True)
    projektstatus.drop(op.get_bind(), checkfirst=True)
