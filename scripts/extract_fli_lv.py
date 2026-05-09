"""
extract_fli_lv.py - Batch-Extraktion der 61 FLI-LV-PDFs

Fixes v2:
- nummernkreis als int (DB ist smallint)
- LV 002 wird uebersprungen (Index-Datei)
- sys.path direkt auf lv_extraktion (kein __init__.py-Import)
- Duplikat-Check vor Insert
"""
import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

# Modul-Pfade fuer direkte Imports (ohne __init__.py / Router / Config)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api", "lv_extraktion"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("extract_fli_lv")

# LVs die uebersprungen werden sollen
SKIP_LV_NUMMERN = {"002"}  # 002 = Index-Datei, kein echtes LV


def parse_lv_filename(filename: str) -> dict:
    """LV-Nummer und Metadaten aus dem Dateinamen parsen."""
    name = Path(filename).stem

    match = re.search(r"(\d{3})", name)
    if not match:
        return {"nummer": None, "bezeichnung": name, "nummernkreis": None}

    nummer = match.group(1)

    # Nummernkreis als int (DB ist smallint)
    erste_stelle = int(nummer[0])
    nummernkreis_map = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    nummernkreis = nummernkreis_map.get(erste_stelle, 0)

    rest = re.sub(r"^.*?\d{3}[_\-\s]*", "", name).strip()
    if rest:
        bezeichnung = rest.replace("_", " ").replace("-", " ").strip()
    else:
        bezeichnung = f"LV {nummer}"

    return {
        "nummer": nummer,
        "bezeichnung": bezeichnung,
        "nummernkreis": nummernkreis,
    }


def main():
    parser = argparse.ArgumentParser(description="FLI LV-PDFs extrahieren")
    parser.add_argument("--lv-pfad", required=True, help="Pfad zu den LV-PDFs")
    parser.add_argument("--projekt", default="FLI", help="Projektkuerzel")
    parser.add_argument("--docling-url", default=None, help="spark-docling URL")
    parser.add_argument("--db-url", default=None, help="PostgreSQL Connection String")
    parser.add_argument("--dry-run", action="store_true", help="Nur Dateinamen analysieren")
    parser.add_argument("--limit", type=int, default=0, help="Nur N PDFs verarbeiten")
    args = parser.parse_args()

    lv_pfad = Path(args.lv_pfad)
    if not lv_pfad.exists():
        logger.error(f"Pfad nicht gefunden: {lv_pfad}")
        sys.exit(1)

    pdf_files = sorted(lv_pfad.glob("*.pdf")) + sorted(lv_pfad.glob("*.PDF"))
    # Deduplizieren (falls *.pdf und *.PDF dasselbe matchen)
    seen = set()
    unique_pdfs = []
    for p in pdf_files:
        if p.name.lower() not in seen:
            seen.add(p.name.lower())
            unique_pdfs.append(p)
    pdf_files = unique_pdfs

    logger.info(f"{len(pdf_files)} PDF-Dateien gefunden in {lv_pfad}")

    if args.limit > 0:
        pdf_files = pdf_files[:args.limit]
        logger.info(f"Begrenzt auf {args.limit} Dateien (--limit)")

    # LV 002 und andere Skip-Nummern filtern
    filtered = []
    for pdf in pdf_files:
        meta = parse_lv_filename(pdf.name)
        if meta["nummer"] in SKIP_LV_NUMMERN:
            logger.info(f"Uebersprungen (Skip-Liste): {pdf.name} (LV {meta['nummer']})")
            continue
        filtered.append(pdf)

    skipped = len(pdf_files) - len(filtered)
    if skipped > 0:
        logger.info(f"{skipped} LVs uebersprungen (Skip-Liste: {SKIP_LV_NUMMERN})")
    pdf_files = filtered

    if args.dry_run:
        logger.info("=== DRY RUN ===")
        for pdf in pdf_files:
            meta = parse_lv_filename(pdf.name)
            vs_nfd = " [VS-NfD!]" if meta["nummer"] == "211" else ""
            logger.info(f"  {pdf.name} -> Nr: {meta['nummer']}, "
                        f"NK: {meta['nummernkreis']}, "
                        f"Bez: {meta['bezeichnung']}{vs_nfd}")
        logger.info(f"Gesamt: {len(pdf_files)} PDFs (wuerden verarbeitet)")
        return

    # Imports fuer den echten Lauf
    from docling_client import DoclingClient
    from lv_parser import parse_lv_tables
    from service import LVService
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    db_url = args.db_url or os.getenv(
        "DATABASE_URL",
        "postgresql://baupilot:baupilot@localhost:5436/baupilot"
    )
    docling_url = args.docling_url or os.getenv("DOCLING_URL", "http://localhost:8070")

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    client = DoclingClient(base_url=docling_url)

    # Health Check
    health = client.health()
    if health.get("status") != "ok":
        logger.error(f"spark-docling nicht erreichbar: {health}")
        sys.exit(1)
    logger.info(f"spark-docling erreichbar: {health}")

    erfolg = 0
    fehler = 0
    uebersprungen = 0
    gesamt_positionen = 0
    start_gesamt = time.time()

    for i, pdf_file in enumerate(pdf_files, 1):
        meta = parse_lv_filename(pdf_file.name)
        if not meta["nummer"]:
            logger.warning(f"[{i}/{len(pdf_files)}] Keine LV-Nummer: {pdf_file.name}")
            fehler += 1
            continue

        logger.info(f"[{i}/{len(pdf_files)}] Verarbeite LV {meta['nummer']}: {pdf_file.name}")
        start = time.time()

        db = SessionLocal()
        try:
            svc = LVService(db)

            # Duplikat-Check: existiert das LV schon?
            existing = db.execute(text("""
                SET LOCAL search_path TO tenant_tlbv, shared, public;
                SELECT id FROM leistungsverzeichnisse
                WHERE nummer = :nummer
            """), {"nummer": meta["nummer"]}).fetchone()

            if existing:
                lv_id = str(existing[0])
                # Positionen zaehlen via lv_positionen
                pos_count = db.execute(text("""
                    SELECT COUNT(*) FROM lv_positionen
                    WHERE lv_id = CAST(:lv_id AS UUID)
                """), {"lv_id": lv_id}).scalar() or 0

                if pos_count > 0:
                    logger.info(f"  LV {meta['nummer']} existiert bereits mit {pos_count} Positionen - uebersprungen")
                    uebersprungen += 1
                    db.close()
                    continue
                else:
                    # Alte (partielle) Positionen loeschen
                    del_count = db.execute(text("""
                        DELETE FROM lv_positionen
                        WHERE lv_id = CAST(:lv_id AS UUID)
                    """), {"lv_id": lv_id}).rowcount
                    db.commit()
                    if del_count > 0:
                        logger.info(f"  {del_count} alte Positionen geloescht")
                    logger.info(f"  LV {meta['nummer']} existiert ohne Positionen - fuege hinzu")
            else:
                klassifikation = "vs_nfd" if meta["nummer"] == "211" else "intern"
                lv_id = svc.lv_anlegen(
                    projekt_kurz=args.projekt,
                    nummer=meta["nummer"],
                    bezeichnung=meta["bezeichnung"],
                    dateiname=pdf_file.name,
                    nummernkreis=meta["nummernkreis"],
                    klassifikation=klassifikation,
                )

            # PDF an Docling senden (pdfplumber-Fallback bei Timeout)
            pdf_bytes = pdf_file.read_bytes()
            try:
                result = client.extract_tables(pdf_bytes, pdf_file.name)
            except Exception as docling_err:
                err_msg = str(docling_err).lower()
                if "timed out" in err_msg or "timeout" in err_msg:
                    logger.warning(f"  Docling Timeout, versuche pdfplumber-Fallback...")
                    try:
                        result = client.extract_tables(pdf_bytes, pdf_file.name, extractor="pdfplumber")
                        logger.info(f"  pdfplumber-Fallback erfolgreich")
                    except Exception as fb_err:
                        logger.error(f"  pdfplumber-Fallback fehlgeschlagen: {fb_err}")
                        raise fb_err
                else:
                    raise

            tables = result if isinstance(result, list) else result.get("tables", [])
            logger.info(f"  Docling: {len(tables)} Tabellen extrahiert")

            # Tabellen parsen
            positionen = parse_lv_tables(tables)
            logger.info(f"  Parser: {len(positionen)} Positionen erkannt")

            if not positionen:
                svc.lv_status_setzen(lv_id, "fehler", 0)
                logger.warning(f"  Keine Positionen - manuell pruefen")
                fehler += 1
                db.close()
                continue

            # Positionen speichern
            count = svc.positionen_einfuegen(
                lv_id=lv_id,
                positionen=positionen,
                extractor="docling",
            )

            svc.lv_status_setzen(lv_id, "abgeschlossen", count)

            dauer = time.time() - start
            logger.info(f"  OK: {count} Positionen in {dauer:.1f}s")
            erfolg += 1
            gesamt_positionen += count

        except Exception as e:
            logger.error(f"  FEHLER: {e}")
            fehler += 1
        finally:
            db.close()

    dauer_gesamt = time.time() - start_gesamt
    logger.info("=" * 60)
    logger.info(f"FERTIG in {dauer_gesamt:.0f}s ({dauer_gesamt/60:.1f} min)")
    logger.info(f"Erfolg: {erfolg}, Fehler: {fehler}, Uebersprungen: {uebersprungen}")
    logger.info(f"Positionen gesamt: {gesamt_positionen}")


if __name__ == "__main__":
    main()