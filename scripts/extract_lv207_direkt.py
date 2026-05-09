"""Direktextraktion LV 207 via pdfplumber (ohne spark-docling)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api", "lv_extraktion"))

import pdfplumber
from lv_parser import parse_lv_tables
from service import LVService
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PDF = r"P:\Datenübergabe FLI\01_LV\207 Dämmarbeiten LT.pdf"
DB = "postgresql://baupilot:CHANGE_ME_IN_PRODUCTION@localhost:5436/baupilot"

print(f"Oeffne {PDF}...")
pdf = pdfplumber.open(PDF)
print(f"  {len(pdf.pages)} Seiten")

tables = []
for i, page in enumerate(pdf.pages):
    page_tables = page.extract_tables()
    for t in (page_tables or []):
        if len(t) > 1:
            tables.append({"header": t[0], "rows": t[1:]})
    if (i+1) % 20 == 0:
        print(f"  Seite {i+1}/{len(pdf.pages)}...")

print(f"  {len(tables)} Tabellen extrahiert")
pdf.close()

positionen = parse_lv_tables(tables)
print(f"  {len(positionen)} Positionen geparst")

if not positionen:
    print("  KEINE POSITIONEN - manuell pruefen")
    sys.exit(1)

engine = create_engine(DB)
db = sessionmaker(bind=engine)()
db.execute(text("SET LOCAL search_path TO tenant_tlbv, shared, public"))

lv_id = db.execute(text("SELECT id FROM leistungsverzeichnisse WHERE nummer = '207'")).scalar()
if not lv_id:
    print("  LV 207 nicht gefunden!")
    sys.exit(1)

db.execute(text("DELETE FROM lv_positionen WHERE lv_id = CAST(:id AS UUID)"), {"id": str(lv_id)})
db.commit()

svc = LVService(db)
count = svc.positionen_einfuegen(lv_id=str(lv_id), positionen=positionen, extractor="pdfplumber-direkt")
print(f"  OK: {count} Positionen eingefuegt")
db.close()