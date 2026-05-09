"""LV 207 Direktextraktion via pdfplumber TEXT (keine Tabellenerkennung)."""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api", "lv_extraktion"))

import pdfplumber
from decimal import Decimal, InvalidOperation
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PDF = r"P:\Datenübergabe FLI\01_LV\207 Dämmarbeiten LT.pdf"
DB = "postgresql://baupilot:CHANGE_ME_IN_PRODUCTION@localhost:5436/baupilot"

# OZ-Pattern: 207.1.1.10 oder 207. 1. 1. 10
RE_OZ = re.compile(r"^(\d{3}(?:\s*\.\s*\d+){1,3})\s+(.+)", re.MULTILINE)
RE_GERMAN_NUM = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?)")
RE_OZ_CLEAN = re.compile(r"\s*\.\s*")

KNOWN_UNITS = ["m2","m3","m","m²","m³","kg","t","l","Stck","Stk","St","psch","pauschal",
               "PA","Psch","lfm","Lfm","cm","mm","h","Std","Tag","Tage","kN"]

def parse_german(s):
    if not s: return None
    c = s.strip().replace(" ","").replace("\u00a0","").replace("€","").replace("EUR","")
    if "," in c and "." in c: c = c.replace(".","").replace(",",".")
    elif "," in c: c = c.replace(",",".")
    try: return Decimal(c)
    except: return None

print(f"Oeffne {PDF}...")
pdf = pdfplumber.open(PDF)
print(f"  {len(pdf.pages)} Seiten")

positionen = []
for i, page in enumerate(pdf.pages):
    try:
        txt = page.extract_text() or ""
    except:
        continue
    for m in RE_OZ.finditer(txt):
        oz_raw = RE_OZ_CLEAN.sub(".", m.group(1).strip()).strip(".")
        rest = m.group(2).strip()
        # Menge + Einheit + Kurztext aus Rest extrahieren
        menge = None; einheit = None; kurztext = rest
        num_m = RE_GERMAN_NUM.match(rest)
        if num_m:
            menge = parse_german(num_m.group(1))
            after = rest[num_m.end():].strip()
            for u in KNOWN_UNITS:
                if after.lower().startswith(u.lower()):
                    einheit = u
                    kurztext = after[len(u):].strip()
                    break
            else:
                tokens = after.split(None, 1)
                if tokens and len(tokens[0]) <= 5:
                    einheit = tokens[0]
                    kurztext = tokens[1].strip() if len(tokens) > 1 else ""
                else:
                    kurztext = after
        positionen.append({
            "oz": oz_raw, "kurztext": kurztext[:500] if kurztext else "",
            "langtext": kurztext if kurztext and len(kurztext) > 500 else None,
            "menge": menge, "einheit": einheit,
            "einheitspreis": None, "gesamtpreis": None,
            "hierarchie_ebene": len(oz_raw.split(".")) - 1 if len(oz_raw.split(".")) <= 3 else 0,
            "ist_titel": menge is None,
            "roh_text": rest[:500],
        })
    if (i+1) % 20 == 0:
        print(f"  Seite {i+1}/{len(pdf.pages)}, {len(positionen)} Positionen bisher...")

pdf.close()
print(f"  {len(positionen)} Positionen aus Text extrahiert")

if not positionen:
    print("  KEINE POSITIONEN")
    sys.exit(1)

engine = create_engine(DB)
db = sessionmaker(bind=engine)()
db.execute(text("SET search_path TO tenant_tlbv, shared, public"))
lv_id = db.execute(text("SELECT id FROM leistungsverzeichnisse WHERE nummer = '207'")).scalar()
if not lv_id:
    print("  LV 207 nicht gefunden!"); sys.exit(1)

db.execute(text("DELETE FROM lv_positionen WHERE lv_id = CAST(:id AS UUID)"), {"id": str(lv_id)})
db.commit()

import uuid
from datetime import datetime, timezone
count = 0
for pos in positionen:
    try:
        db.execute(text("""
            INSERT INTO lv_positionen
                (id, lv_id, oz, kurztext, langtext, menge, einheit,
                 einheitspreis, gesamtpreis, hierarchie_ebene, ist_titel,
                 extrahiert_am, extrahiert_mit, roh_text,
                 erstellt_am, erstellt_von, geaendert_am, geaendert_von, geloescht)
            VALUES
                (CAST(:id AS UUID), CAST(:lv_id AS UUID), :oz, :kurztext, :langtext,
                 :menge, :einheit, :ep, :gp, :hierarchie, :ist_titel,
                 CAST(:ext_am AS TIMESTAMPTZ), :ext_mit, :roh,
                 NOW(), 'system', NOW(), 'system', FALSE)
            ON CONFLICT (lv_id, oz) DO NOTHING
        """), {
            "id": str(uuid.uuid4()), "lv_id": str(lv_id),
            "oz": pos["oz"], "kurztext": pos["kurztext"], "langtext": pos["langtext"],
            "menge": float(pos["menge"]) if pos["menge"] else None,
            "einheit": pos["einheit"], "ep": None, "gp": None,
            "hierarchie": pos["hierarchie_ebene"], "ist_titel": pos["ist_titel"],
            "ext_am": datetime.now(timezone.utc).isoformat(),
            "ext_mit": "pdfplumber-text", "roh": pos["roh_text"],
        })
        count += 1
    except Exception as e:
        print(f"  Fehler bei {pos['oz']}: {e}")
        db.rollback()
        continue
db.commit()
print(f"  OK: {count} Positionen eingefuegt (Text-Modus, ohne EP/GP)")
db.close()