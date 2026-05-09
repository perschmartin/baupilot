"""
LV-Parser: Konvertiert Docling-Ausgabe in strukturierte LV-Positionen.

Tatsaechliches Format der FLI-LVs (Docling Markdown-Tabellen):
    | Ordnungszahl   | Menge Einheit                                    | Einheitspreis | Waehrung | Gesamtpreis |
    | 106. 1. 1. 20  | 8.000,00 m2 Sauberkeitsschicht C 12/15, d = 5 cm | 12,63         | EUR      | 101.040,00  |

Fixes gegenueber v1:
- Kombinierte "Menge Einheit [Kurztext]"-Spalte wird aufgeteilt
- OZ normalisiert: "106. 1. 1. 10" -> "106.1.1.10"
- Summenzeilen ("Summe 106. 1. 1 ...") werden gefiltert
- 4 Header-Varianten unterstuetzt
- Bekannte Baubranche-Einheiten (m2, m3, psch, lfm, Stck, ...)

Autor: Claude fuer BauPilot AP 1.2
"""
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

logger = logging.getLogger("baupilot.lv_parser")

KNOWN_UNITS = sorted([
    "m2", "m3", "m", "m²", "m³", "kg", "t", "l", "dl",
    "Stck", "Stk", "St", "Stück", "psch", "pauschal", "PA", "Psch",
    "lfm", "lfdm", "Lfm", "cm", "mm", "km",
    "h", "Std", "Tag", "Tage", "kN", "kNm",
], key=len, reverse=True)

_RE_GERMAN_NUMBER = re.compile(r"^(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)")
_RE_SUMMENZEILE = re.compile(r"^\s*Summe\s", re.IGNORECASE)
_RE_OZ_SPACES = re.compile(r"\s*\.\s*")


def parse_lv_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parst extrahierte Tabellen in LV-Positionen."""
    positionen = []
    for tbl_idx, table in enumerate(tables):
        header = table.get("header", [])
        rows = table.get("rows", [])
        if not rows:
            continue
        mapping = _detect_column_mapping(header)
        if not mapping:
            logger.debug(f"Tabelle {tbl_idx} uebersprungen - kein LV-Mapping: {header}")
            continue
        logger.info(f"Tabelle {tbl_idx}: {len(rows)} Zeilen, Mapping: {mapping}")
        for row_idx, row in enumerate(rows):
            try:
                pos = _parse_row(row, mapping)
                if pos:
                    positionen.append(pos)
            except Exception as e:
                logger.warning(f"Tabelle {tbl_idx} Zeile {row_idx}: {e}")
    logger.info(f"Insgesamt {len(positionen)} LV-Positionen geparst")
    return positionen


def _detect_column_mapping(header: list[str]) -> Optional[dict[str, int]]:
    """
    4 Header-Varianten:
      1. [Ordnungszahl, Menge Einheit, Einheitspreis, Waehrung, Gesamtpreis]
      2. [Ordnungszahl, Menge Einheit Kurztext, Einheitspreis, Waehrung, Gesamtpreis]
      3. [OZ, Menge Einheit, EP, Waehrung, GP]
      4. [Pos, Text, Menge, Einheit, EP, GP]  (klassisches GAEB)
    """
    if not header:
        return None
    mapping = {}
    hl = [h.lower().strip() for h in header]

    # Kombinierte Spalte (Variante 1-3)
    for i, h in enumerate(hl):
        if "menge" in h and ("einheit" in h or "einh" in h):
            mapping["menge_einheit"] = i
            break

    # OZ
    for i, h in enumerate(hl):
        if any(h == p or h.startswith(p + " ") or h.startswith(p + ".")
               for p in ["ordnungszahl", "oz", "pos", "pos.", "position", "pos-nr", "nr", "nr.", "lfd. nr"]):
            mapping["oz"] = i
            break

    # Variante 4: Getrennte Spalten
    if "menge_einheit" not in mapping:
        for i, h in enumerate(hl):
            if any(p in h for p in ["kurztext", "text", "beschreibung", "leistung", "bezeichnung"]):
                mapping["kurztext"] = i
                break
        for i, h in enumerate(hl):
            if any(h == p or h.startswith(p) for p in ["menge", "mng", "anz"]):
                if "einheit" not in h and "einh" not in h:
                    mapping["menge"] = i
                    break
        for i, h in enumerate(hl):
            if any(h == p or h.startswith(p) for p in ["einheit", "einh", "eh", "me"]):
                if "menge" not in h and "preis" not in h:
                    mapping["einheit"] = i
                    break

    # EP
    for i, h in enumerate(hl):
        if any(h == p or h.startswith(p) for p in ["einheitspreis", "ep", "e-preis", "e.p.", "einzelpreis"]):
            mapping["ep"] = i
            break

    # GP
    for i, h in enumerate(hl):
        if any(h == p or h.startswith(p) for p in ["gesamtpreis", "gp", "gesamtbetrag", "g-preis", "betrag", "gesamt"]):
            mapping["gp"] = i
            break

    if not any(k in mapping for k in ("oz", "menge_einheit", "kurztext")):
        return None
    return mapping


def _parse_row(row: list[str], mapping: dict[str, int]) -> Optional[dict[str, Any]]:
    def get_cell(key: str) -> str:
        idx = mapping.get(key)
        if idx is not None and idx < len(row):
            return (row[idx] or "").strip()
        return ""

    roh_text = " | ".join(str(c) for c in row)
    oz = _normalize_oz(get_cell("oz"))

    if "menge_einheit" in mapping:
        me_text = get_cell("menge_einheit")
        if not oz and not me_text:
            return None
        if _RE_SUMMENZEILE.match(me_text):
            return None
        # Reine Strukturtexte ohne OZ und ohne Zahl ueberspringen
        if not oz and not _RE_GERMAN_NUMBER.match(me_text):
            if len(me_text) < 3 or me_text.lower() in ("vorbemerkungen", "anlagenverzeichnis", "technische"):
                return None
        menge, einheit, kurztext = _split_menge_einheit_text(me_text)
    else:
        kurztext = get_cell("kurztext")
        einheit = get_cell("einheit") or None
        menge = _parse_german_decimal(get_cell("menge"))
        if not oz and not kurztext:
            return None
        if kurztext and _RE_SUMMENZEILE.match(kurztext):
            return None

    ep = _parse_german_decimal(get_cell("ep"))
    gp = _parse_german_decimal(get_cell("gp"))
    ist_titel = (menge is None and ep is None and gp is None and bool(kurztext or oz))
    hierarchie = _detect_hierarchy(oz)

    if not oz and not kurztext and menge is None:
        return None

    # Fallback-Werte fuer NOT-NULL-Spalten in der DB
    if not oz and menge is None:
        # Strukturzeile ohne OZ und ohne Menge (z.B. "Technische Vorbemerkungen")
        # -> ueberspringen, kein echter LV-Eintrag
        return None

    # --- Einheit-Guard (Fix Volllauf Sitzung 5) ---
    # Parser schreibt bei Titel-Zeilen den Kurztext ins Einheit-Feld.
    # Echte Einheiten sind nie laenger als ~10 Zeichen (m, m2, St, psch, ...)
    if einheit and len(einheit) > 20:
        if not kurztext:
            kurztext = einheit
        einheit = None
        menge = None

    # Kurztext > 500 Zeichen: Ueberschuss in Langtext verschieben
    langtext = None
    if kurztext and len(kurztext) > 500:
        langtext = kurztext
        dot_pos = kurztext[:200].rfind(".")
        if dot_pos > 50:
            kurztext = kurztext[:dot_pos + 1]
        else:
            kurztext = kurztext[:200] + "..."

    return {
        "oz": oz or "", "kurztext": kurztext or "", "langtext": langtext,
        "menge": menge, "einheit": einheit,
        "einheitspreis": ep, "gesamtpreis": gp,
        "hierarchie_ebene": hierarchie, "ist_titel": ist_titel,
        "roh_text": roh_text,
    }


def _split_menge_einheit_text(combined: str) -> tuple[Optional[Decimal], Optional[str], Optional[str]]:
    """
    "8.000,00 m2 Sauberkeitsschicht C 12/15" -> (8000.00, "m2", "Sauberkeitsschicht C 12/15")
    "Stahlbetonarbeiten"                      -> (None, None, "Stahlbetonarbeiten")
    """
    if not combined or not combined.strip():
        return None, None, None
    text = combined.strip()

    m = _RE_GERMAN_NUMBER.match(text)
    if not m:
        return None, None, text

    menge = _parse_german_decimal(m.group(1))
    rest = text[m.end():].strip()
    einheit = None
    kurztext = None

    if rest:
        einheit_match = _match_unit(rest)
        if einheit_match:
            einheit = einheit_match
            kt = rest[len(einheit):].strip()
            kurztext = kt if kt else None
        else:
            tokens = rest.split(None, 1)
            if len(tokens[0]) <= 5 and not _RE_GERMAN_NUMBER.match(tokens[0]):
                einheit = tokens[0]
                kurztext = tokens[1].strip() if len(tokens) > 1 else None
            else:
                kurztext = rest

    return menge, einheit, kurztext


def _match_unit(text: str) -> Optional[str]:
    for unit in KNOWN_UNITS:
        if text.lower().startswith(unit.lower()):
            after = text[len(unit):]
            if not after or after[0] in (" ", "\t", ",", ";"):
                return text[:len(unit)]
    return None


def _normalize_oz(oz_raw: str) -> Optional[str]:
    """'106. 1. 1. 10' -> '106.1.1.10'"""
    if not oz_raw or not oz_raw.strip():
        return None
    cleaned = _RE_OZ_SPACES.sub(".", oz_raw.strip()).strip(".")
    return cleaned if cleaned else None


def _parse_german_decimal(value: str) -> Optional[Decimal]:
    if not value:
        return None
    cleaned = value.strip().replace(" ", "").replace("\u00a0", "")
    cleaned = cleaned.replace("€", "").replace("EUR", "").strip()
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    if not re.match(r"^-?\d+\.?\d*$", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _detect_hierarchy(oz: Optional[str]) -> int:
    """106->1, 106.1->2, 106.1.1->3, 106.1.1.10->0 (Position)"""
    if not oz:
        return 0
    n = len(oz.split("."))
    if n <= 1: return 1
    elif n == 2: return 2
    elif n == 3: return 3
    else: return 0