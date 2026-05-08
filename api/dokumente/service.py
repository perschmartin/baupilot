"""
Dokumente-Service (AP 1.5).
Geschaeftslogik fuer Upload, Download, Versionierung, Verknuepfung.
Folgt dem Service-Pattern wie AuthService und AufgabenService.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from storage.minio_service import (
    get_minio_client,
    bucket_name_for_mandant,
    build_object_path,
    upload_file as minio_upload,
    download_file as minio_download,
    ist_erlaubter_mime_typ,
    ist_erlaubte_groesse,
)

logger = logging.getLogger("baupilot.dokumente")


class DokumenteService:
    def __init__(self, db: Session):
        self.db = db
        self.minio = get_minio_client()

    # ----------------------------------------------------------------
    # Upload
    # ----------------------------------------------------------------
    def upload(
        self,
        datei_bytes: bytes,
        dateiname: str,
        mime_typ: str,
        projekt_kurz: str,
        kategorie: str = "sonstiges",
        beschreibung: Optional[str] = None,
        vorgang_id: Optional[str] = None,
        mandant_slug: str = "tlbv",
        benutzer_email: str = "system",
    ) -> dict:
        """Laedt ein Dokument hoch und speichert Metadaten in DB + MinIO."""

        # 1. Validierung
        if not ist_erlaubter_mime_typ(mime_typ, dateiname):
            return {"fehler": "mime_typ_nicht_erlaubt", "detail": f"MIME-Typ '{mime_typ}' oder Dateiendung nicht erlaubt"}

        if not ist_erlaubte_groesse(len(datei_bytes)):
            return {"fehler": "datei_zu_gross", "detail": f"Dateigroesse {len(datei_bytes)} Bytes ueberschreitet Limit"}

        # 2. SHA-256 berechnen
        sha256 = hashlib.sha256(datei_bytes).hexdigest()

        # 3. Duplikat-Check
        duplikat_warnung = None
        dup = self.db.execute(
            text("SELECT id, dateiname FROM dokumente WHERE sha256_hash = :hash AND geloescht = false LIMIT 1"),
            {"hash": sha256}
        ).fetchone()
        if dup:
            duplikat_warnung = f"Identische Datei existiert bereits: {dup[1]} (ID: {dup[0]})"

        # 4. Projekt-ID aufloesen
        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :kurz"),
            {"kurz": projekt_kurz}
        ).fetchone()
        if not projekt:
            return {"fehler": "projekt_nicht_gefunden", "detail": f"Projekt '{projekt_kurz}' nicht gefunden"}
        projekt_id = str(projekt[0])

        # 5. Dokument-ID generieren
        dok_id = str(uuid.uuid4())

        # 6. MinIO-Upload
        bucket = bucket_name_for_mandant(mandant_slug)
        object_path = build_object_path(projekt_kurz, dok_id, 1, dateiname)

        try:
            minio_upload(self.minio, bucket, object_path, datei_bytes, mime_typ)
        except Exception as e:
            logger.error(f"MinIO-Upload fehlgeschlagen: {e}")
            return {"fehler": "minio_upload_fehler", "detail": str(e)}

        # 7. DB-Eintrag (dateipfad_minio fuer Kompatibilitaet mit Migration 001)
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            text("""
                INSERT INTO dokumente (
                    id, projekt_id, dateiname, mime_typ, dateigroesse_bytes,
                    sha256_hash, kategorie, beschreibung, version_nummer,
                    minio_bucket, minio_pfad, dateipfad_minio,
                    signatur_status, gesperrt, geloescht,
                    erstellt_am, erstellt_von, geaendert_am, geaendert_von
                ) VALUES (
                    CAST(:id AS UUID), CAST(:projekt_id AS UUID),
                    :dateiname, :mime_typ, :groesse,
                    :sha256, CAST(:kategorie AS dokumentkategorie), :beschreibung, 1,
                    :bucket, :pfad, :pfad,
                    CAST('nicht_signiert' AS signaturstatus),
                    false, false,
                    :now, :benutzer, :now, :benutzer
                )
            """),
            {
                "id": dok_id,
                "projekt_id": projekt_id,
                "dateiname": dateiname,
                "mime_typ": mime_typ,
                "groesse": len(datei_bytes),
                "sha256": sha256,
                "kategorie": kategorie,
                "beschreibung": beschreibung,
                "bucket": bucket,
                "pfad": object_path,
                "now": now,
                "benutzer": benutzer_email,
            }
        )

        # 8. Optional: Verknuepfung mit Vorgang
        if vorgang_id:
            self._verknuepfen(dok_id, vorgang_id, benutzer_email)

        self.db.commit()

        logger.info(f"Dokument hochgeladen: {dateiname} ({dok_id})")

        return {
            "id": dok_id,
            "dateiname": dateiname,
            "version_nummer": 1,
            "sha256_hash": sha256,
            "dateigroesse_bytes": len(datei_bytes),
            "kategorie": kategorie,
            "duplikat_warnung": duplikat_warnung,
        }

    # ----------------------------------------------------------------
    # Neue Version
    # ----------------------------------------------------------------
    def neue_version(
        self,
        dokument_id: str,
        datei_bytes: bytes,
        dateiname: str,
        mime_typ: str,
        mandant_slug: str = "tlbv",
        benutzer_email: str = "system",
    ) -> dict:
        """Erstellt eine neue Version eines bestehenden Dokuments."""

        # Altes Dokument laden
        alt = self.db.execute(
            text("""
                SELECT id, projekt_id, version_nummer, gesperrt, dateiname,
                       kategorie, beschreibung
                FROM dokumente
                WHERE id = CAST(:id AS UUID) AND geloescht = false
            """),
            {"id": dokument_id}
        ).fetchone()

        if not alt:
            return {"fehler": "nicht_gefunden", "detail": "Dokument nicht gefunden"}

        if alt[3]:  # gesperrt
            return {"fehler": "gesperrt", "detail": "Signiertes Dokument kann nicht ueberschrieben werden"}

        # Validierung
        if not ist_erlaubter_mime_typ(mime_typ, dateiname):
            return {"fehler": "mime_typ_nicht_erlaubt", "detail": f"MIME-Typ '{mime_typ}' nicht erlaubt"}
        if not ist_erlaubte_groesse(len(datei_bytes)):
            return {"fehler": "datei_zu_gross", "detail": "Datei zu gross"}

        sha256 = hashlib.sha256(datei_bytes).hexdigest()
        neue_version_nr = alt[2] + 1
        neues_id = str(uuid.uuid4())
        projekt_id = str(alt[1])

        # Projekt-Kuerzel fuer Pfad
        projekt = self.db.execute(
            text("SELECT kurz FROM projekte WHERE id = CAST(:id AS UUID)"),
            {"id": projekt_id}
        ).fetchone()
        projekt_kurz = projekt[0] if projekt else "UNKNOWN"

        # MinIO-Upload
        bucket = bucket_name_for_mandant(mandant_slug)
        object_path = build_object_path(projekt_kurz, neues_id, neue_version_nr, dateiname)

        try:
            minio_upload(self.minio, bucket, object_path, datei_bytes, mime_typ)
        except Exception as e:
            return {"fehler": "minio_upload_fehler", "detail": str(e)}

        # DB-Eintrag
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            text("""
                INSERT INTO dokumente (
                    id, projekt_id, dateiname, mime_typ, dateigroesse_bytes,
                    sha256_hash, kategorie, beschreibung,
                    version_nummer, vorgaenger_version_id,
                    minio_bucket, minio_pfad, dateipfad_minio,
                    signatur_status, gesperrt, geloescht,
                    erstellt_am, erstellt_von, geaendert_am, geaendert_von
                ) VALUES (
                    CAST(:id AS UUID), CAST(:projekt_id AS UUID),
                    :dateiname, :mime_typ, :groesse,
                    :sha256, CAST(:kategorie AS dokumentkategorie), :beschreibung,
                    :version, CAST(:vorgaenger AS UUID),
                    :bucket, :pfad, :pfad,
                    CAST('nicht_signiert' AS signaturstatus),
                    false, false,
                    :now, :benutzer, :now, :benutzer
                )
            """),
            {
                "id": neues_id,
                "projekt_id": projekt_id,
                "dateiname": dateiname,
                "mime_typ": mime_typ,
                "groesse": len(datei_bytes),
                "sha256": sha256,
                "kategorie": str(alt[5]),
                "beschreibung": alt[6],
                "version": neue_version_nr,
                "vorgaenger": dokument_id,
                "bucket": bucket,
                "pfad": object_path,
                "now": now,
                "benutzer": benutzer_email,
            }
        )

        # Verknuepfungen uebernehmen
        self.db.execute(
            text("""
                INSERT INTO vorgang_dokumente (vorgang_id, dokument_id, verknuepfungstyp, erstellt_von)
                SELECT vorgang_id, CAST(:neues_id AS UUID), verknuepfungstyp, :benutzer
                FROM vorgang_dokumente
                WHERE dokument_id = CAST(:altes_id AS UUID)
                ON CONFLICT (vorgang_id, dokument_id) DO NOTHING
            """),
            {"neues_id": neues_id, "altes_id": dokument_id, "benutzer": benutzer_email}
        )

        self.db.commit()
        logger.info(f"Neue Version {neue_version_nr} fuer Dokument {dokument_id}")

        return {
            "id": neues_id,
            "dateiname": dateiname,
            "version_nummer": neue_version_nr,
            "sha256_hash": sha256,
            "dateigroesse_bytes": len(datei_bytes),
            "kategorie": str(alt[5]),
        }

    # ----------------------------------------------------------------
    # Download
    # ----------------------------------------------------------------
    def download(self, dokument_id: str) -> tuple:
        """Gibt (bytes, dateiname, mime_typ) zurueck oder (None, fehler, None)."""
        dok = self.db.execute(
            text("""
                SELECT minio_bucket, minio_pfad, dateiname, mime_typ
                FROM dokumente
                WHERE id = CAST(:id AS UUID) AND geloescht = false
            """),
            {"id": dokument_id}
        ).fetchone()

        if not dok:
            return None, "Dokument nicht gefunden", None

        try:
            data = minio_download(self.minio, dok[0], dok[1])
            return data, dok[2], dok[3]
        except Exception as e:
            logger.error(f"Download-Fehler: {e}")
            return None, str(e), None

    # ----------------------------------------------------------------
    # Liste & Detail
    # ----------------------------------------------------------------
    def liste(
        self,
        projekt_kurz: str,
        kategorie: Optional[str] = None,
        suche: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        """Dokumente auflisten mit Filtern."""
        query = """
            SELECT d.id, d.dateiname, d.kategorie, d.version_nummer,
                   d.mime_typ, d.dateigroesse_bytes, d.sha256_hash,
                   d.signatur_status, d.beschreibung,
                   d.erstellt_am, d.erstellt_von
            FROM dokumente d
            JOIN projekte p ON d.projekt_id = p.id
            WHERE d.geloescht = false AND p.kurz = :projekt
        """
        params = {"projekt": projekt_kurz, "limit": limit, "offset": offset}

        if kategorie:
            query += " AND d.kategorie = CAST(:kategorie AS dokumentkategorie)"
            params["kategorie"] = kategorie

        if suche:
            query += " AND (d.dateiname ILIKE :suche OR d.beschreibung ILIKE :suche)"
            params["suche"] = f"%{suche}%"

        query += " ORDER BY d.erstellt_am DESC LIMIT :limit OFFSET :offset"

        rows = self.db.execute(text(query), params).fetchall()
        return [
            {
                "id": str(r[0]), "dateiname": r[1], "kategorie": str(r[2]),
                "version_nummer": r[3], "mime_typ": r[4],
                "dateigroesse_bytes": r[5], "sha256_hash": r[6],
                "signatur_status": str(r[7]), "beschreibung": r[8],
                "erstellt_am": r[9].isoformat() if r[9] else None,
                "erstellt_von": r[10],
            }
            for r in rows
        ]

    def detail(self, dokument_id: str) -> Optional[dict]:
        """Einzelnes Dokument mit allen Metadaten."""
        row = self.db.execute(
            text("""
                SELECT d.id, d.dateiname, d.kategorie, d.version_nummer,
                       d.mime_typ, d.dateigroesse_bytes, d.sha256_hash,
                       d.signatur_status, d.beschreibung,
                       d.erstellt_am, d.erstellt_von,
                       d.projekt_id, d.minio_bucket, d.minio_pfad,
                       d.vorgaenger_version_id, d.signiert_von, d.signiert_am,
                       d.gesperrt, d.geaendert_am, d.geaendert_von
                FROM dokumente d
                WHERE d.id = CAST(:id AS UUID) AND d.geloescht = false
            """),
            {"id": dokument_id}
        ).fetchone()

        if not row:
            return None

        return {
            "id": str(row[0]), "dateiname": row[1], "kategorie": str(row[2]),
            "version_nummer": row[3], "mime_typ": row[4],
            "dateigroesse_bytes": row[5], "sha256_hash": row[6],
            "signatur_status": str(row[7]), "beschreibung": row[8],
            "erstellt_am": row[9].isoformat() if row[9] else None,
            "erstellt_von": row[10],
            "projekt_id": str(row[11]) if row[11] else None,
            "minio_bucket": row[12], "minio_pfad": row[13],
            "vorgaenger_version_id": str(row[14]) if row[14] else None,
            "signiert_von": str(row[15]) if row[15] else None,
            "signiert_am": row[16].isoformat() if row[16] else None,
            "gesperrt": row[17],
            "geaendert_am": row[18].isoformat() if row[18] else None,
            "geaendert_von": row[19],
        }

    def versionen(self, dokument_id: str) -> list:
        """Alle Versionen eines Dokuments (Versionskette verfolgen)."""
        current_id = dokument_id
        alle_ids = [current_id]

        # Vorwaerts: neuere Versionen
        while True:
            newer = self.db.execute(
                text("""
                    SELECT id FROM dokumente
                    WHERE vorgaenger_version_id = CAST(:id AS UUID) AND geloescht = false
                """),
                {"id": current_id}
            ).fetchone()
            if newer:
                current_id = str(newer[0])
                alle_ids.append(current_id)
            else:
                break

        # Rueckwaerts: aeltere Versionen
        current_id = dokument_id
        while True:
            older = self.db.execute(
                text("""
                    SELECT CAST(vorgaenger_version_id AS TEXT) FROM dokumente
                    WHERE id = CAST(:id AS UUID) AND vorgaenger_version_id IS NOT NULL
                """),
                {"id": current_id}
            ).fetchone()
            if older and older[0]:
                current_id = older[0]
                alle_ids.insert(0, current_id)
            else:
                break

        # Deduplizieren und laden
        seen = set()
        unique_ids = []
        for i in alle_ids:
            if i not in seen:
                seen.add(i)
                unique_ids.append(i)

        result = []
        for vid in unique_ids:
            row = self.db.execute(
                text("""
                    SELECT id, version_nummer, dateiname, dateigroesse_bytes,
                           sha256_hash, erstellt_am, erstellt_von
                    FROM dokumente
                    WHERE id = CAST(:id AS UUID) AND geloescht = false
                """),
                {"id": vid}
            ).fetchone()
            if row:
                result.append({
                    "id": str(row[0]), "version_nummer": row[1],
                    "dateiname": row[2], "dateigroesse_bytes": row[3],
                    "sha256_hash": row[4],
                    "erstellt_am": row[5].isoformat() if row[5] else None,
                    "erstellt_von": row[6],
                })

        return sorted(result, key=lambda x: x["version_nummer"])

    # ----------------------------------------------------------------
    # Verknuepfung
    # ----------------------------------------------------------------
    def _verknuepfen(self, dokument_id: str, vorgang_id: str, benutzer: str):
        """Interne Methode: Dokument an Vorgang verknuepfen."""
        self.db.execute(
            text("""
                INSERT INTO vorgang_dokumente (vorgang_id, dokument_id, verknuepfungstyp, erstellt_von)
                VALUES (CAST(:vorgang_id AS UUID), CAST(:dokument_id AS UUID), 'anlage', :benutzer)
                ON CONFLICT (vorgang_id, dokument_id) DO NOTHING
            """),
            {"vorgang_id": vorgang_id, "dokument_id": dokument_id, "benutzer": benutzer}
        )

    def verknuepfen(self, dokument_id: str, vorgang_id: str, verknuepfungstyp: str, benutzer: str) -> dict:
        """Verknuepft ein Dokument mit einem Vorgang."""
        self.db.execute(
            text("""
                INSERT INTO vorgang_dokumente (vorgang_id, dokument_id, verknuepfungstyp, erstellt_von)
                VALUES (CAST(:vorgang_id AS UUID), CAST(:dokument_id AS UUID), :typ, :benutzer)
                ON CONFLICT (vorgang_id, dokument_id) DO NOTHING
            """),
            {"vorgang_id": vorgang_id, "dokument_id": dokument_id, "typ": verknuepfungstyp, "benutzer": benutzer}
        )
        self.db.commit()
        return {"status": "verknuepft", "vorgang_id": vorgang_id, "dokument_id": dokument_id}

    def vorgang_dokumente(self, vorgang_id: str) -> list:
        """Alle Dokumente eines Vorgangs."""
        rows = self.db.execute(
            text("""
                SELECT d.id, d.dateiname, d.kategorie, d.version_nummer,
                       d.mime_typ, d.dateigroesse_bytes, d.signatur_status,
                       d.erstellt_am, d.erstellt_von,
                       vd.verknuepfungstyp
                FROM dokumente d
                JOIN vorgang_dokumente vd ON vd.dokument_id = d.id
                WHERE vd.vorgang_id = CAST(:id AS UUID) AND d.geloescht = false
                ORDER BY d.erstellt_am DESC
            """),
            {"id": vorgang_id}
        ).fetchall()

        return [
            {
                "id": str(r[0]), "dateiname": r[1], "kategorie": str(r[2]),
                "version_nummer": r[3], "mime_typ": r[4],
                "dateigroesse_bytes": r[5], "signatur_status": str(r[6]),
                "erstellt_am": r[7].isoformat() if r[7] else None,
                "erstellt_von": r[8], "verknuepfungstyp": r[9],
            }
            for r in rows
        ]

    # ----------------------------------------------------------------
    # Statistik
    # ----------------------------------------------------------------
    def statistik(self, projekt_kurz: str) -> dict:
        """Dokumentenstatistik pro Projekt."""
        rows = self.db.execute(
            text("""
                SELECT d.kategorie, COUNT(*), COALESCE(SUM(d.dateigroesse_bytes), 0)
                FROM dokumente d
                JOIN projekte p ON d.projekt_id = p.id
                WHERE d.geloescht = false AND p.kurz = :projekt
                GROUP BY d.kategorie
            """),
            {"projekt": projekt_kurz}
        ).fetchall()

        nach_kategorie = {}
        gesamt = 0
        gesamtgroesse = 0
        for r in rows:
            kat = str(r[0])
            nach_kategorie[kat] = r[1]
            gesamt += r[1]
            gesamtgroesse += r[2]

        signiert = self.db.execute(
            text("""
                SELECT COUNT(*) FROM dokumente d
                JOIN projekte p ON d.projekt_id = p.id
                WHERE d.geloescht = false AND p.kurz = :projekt
                AND d.signatur_status = CAST('signiert' AS signaturstatus)
            """),
            {"projekt": projekt_kurz}
        ).scalar() or 0

        return {
            "gesamt": gesamt,
            "nach_kategorie": nach_kategorie,
            "gesamtgroesse_bytes": gesamtgroesse,
            "signiert": signiert,
        }

    # ----------------------------------------------------------------
    # Update & Delete
    # ----------------------------------------------------------------
    def metadaten_update(self, dokument_id: str, kategorie: Optional[str], beschreibung: Optional[str], benutzer: str) -> Optional[dict]:
        """Aktualisiert Metadaten (nur wenn nicht gesperrt)."""
        dok = self.db.execute(
            text("SELECT gesperrt FROM dokumente WHERE id = CAST(:id AS UUID) AND geloescht = false"),
            {"id": dokument_id}
        ).fetchone()

        if not dok:
            return None
        if dok[0]:
            return {"fehler": "gesperrt", "detail": "Signiertes Dokument kann nicht geaendert werden"}

        updates = []
        params = {"id": dokument_id, "benutzer": benutzer, "now": datetime.now(timezone.utc).isoformat()}

        if kategorie:
            updates.append("kategorie = CAST(:kategorie AS dokumentkategorie)")
            params["kategorie"] = kategorie
        if beschreibung is not None:
            updates.append("beschreibung = :beschreibung")
            params["beschreibung"] = beschreibung

        if not updates:
            return self.detail(dokument_id)

        updates.append("geaendert_am = :now")
        updates.append("geaendert_von = :benutzer")

        self.db.execute(
            text(f"UPDATE dokumente SET {', '.join(updates)} WHERE id = CAST(:id AS UUID)"),
            params
        )
        self.db.commit()
        return self.detail(dokument_id)

    def soft_delete(self, dokument_id: str, benutzer: str) -> Optional[dict]:
        """Soft-Delete (nur wenn nicht gesperrt)."""
        dok = self.db.execute(
            text("SELECT gesperrt, dateiname FROM dokumente WHERE id = CAST(:id AS UUID) AND geloescht = false"),
            {"id": dokument_id}
        ).fetchone()

        if not dok:
            return None
        if dok[0]:
            return {"fehler": "gesperrt", "detail": "Signiertes Dokument kann nicht geloescht werden"}

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            text("""
                UPDATE dokumente
                SET geloescht = true, geloescht_am = :now, geloescht_von = :benutzer
                WHERE id = CAST(:id AS UUID)
            """),
            {"id": dokument_id, "now": now, "benutzer": benutzer}
        )
        self.db.commit()
        return {"status": "geloescht", "dateiname": dok[1]}
