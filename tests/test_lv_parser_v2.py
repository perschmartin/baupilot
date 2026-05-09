"""Tests fuer lv_parser.py v2 - kombinierte Menge-Einheit-Spalte."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api", "lv_extraktion"))

from decimal import Decimal
from lv_parser import (
    parse_lv_tables, _split_menge_einheit_text, _normalize_oz,
    _parse_german_decimal, _detect_hierarchy,
)


# --- _split_menge_einheit_text ---

def test_split_menge_einheit_nur_menge():
    m, e, k = _split_menge_einheit_text("8.000,00 m2")
    assert m == Decimal("8000.00")
    assert e == "m2"
    assert k is None

def test_split_menge_einheit_mit_kurztext():
    m, e, k = _split_menge_einheit_text("8.000,00 m2 Sauberkeitsschicht C 12/15, d = 5 cm")
    assert m == Decimal("8000.00")
    assert e == "m2"
    assert k == "Sauberkeitsschicht C 12/15, d = 5 cm"

def test_split_menge_einheit_m3():
    m, e, k = _split_menge_einheit_text("150,00 m3 Fundament, Abtreppung, C 8/10")
    assert m == Decimal("150.00")
    assert e == "m3"
    assert k == "Fundament, Abtreppung, C 8/10"

def test_split_nur_text():
    m, e, k = _split_menge_einheit_text("Stahlbetonarbeiten")
    assert m is None
    assert e is None
    assert k == "Stahlbetonarbeiten"

def test_split_leer():
    m, e, k = _split_menge_einheit_text("")
    assert m is None and e is None and k is None

def test_split_psch():
    m, e, k = _split_menge_einheit_text("1,00 psch Baustelleneinrichtung")
    assert m == Decimal("1.00")
    assert e == "psch"
    assert k == "Baustelleneinrichtung"

def test_split_lfm():
    m, e, k = _split_menge_einheit_text("250,00 lfm Kabel NYM 5x2,5")
    assert m == Decimal("250.00")
    assert e == "lfm"
    assert k == "Kabel NYM 5x2,5"


# --- _normalize_oz ---

def test_oz_mit_leerzeichen():
    assert _normalize_oz("106. 1. 1. 10") == "106.1.1.10"

def test_oz_sauber():
    assert _normalize_oz("106.1.1.10") == "106.1.1.10"

def test_oz_leer():
    assert _normalize_oz("") is None
    assert _normalize_oz("   ") is None

def test_oz_nur_nummer():
    assert _normalize_oz("106") == "106"

def test_oz_zwei_ebenen():
    assert _normalize_oz("106. 1") == "106.1"


# --- _parse_german_decimal ---

def test_deutsch_mit_tausender():
    assert _parse_german_decimal("101.040,00") == Decimal("101040.00")

def test_deutsch_einfach():
    assert _parse_german_decimal("12,63") == Decimal("12.63")

def test_deutsch_gross():
    assert _parse_german_decimal("8.000,00") == Decimal("8000.00")

def test_leer():
    assert _parse_german_decimal("") is None
    assert _parse_german_decimal(None) is None

def test_mit_eur():
    assert _parse_german_decimal("101.040,00 EUR") == Decimal("101040.00")  # Parser entfernt EUR korrekt


# --- _detect_hierarchy ---

def test_hierarchie_hauptgruppe():
    assert _detect_hierarchy("106") == 1

def test_hierarchie_titel1():
    assert _detect_hierarchy("106.1") == 2

def test_hierarchie_titel2():
    assert _detect_hierarchy("106.1.1") == 3

def test_hierarchie_position():
    assert _detect_hierarchy("106.1.1.10") == 0

def test_hierarchie_none():
    assert _detect_hierarchy(None) == 0


# --- Summenzeilen ---

def test_summenzeile_gefiltert():
    tables = [{
        "header": ["Ordnungszahl", "Menge Einheit", "Einheitspreis", "Währung", "Gesamtpreis"],
        "rows": [
            ["106. 1. 1. 10", "8.000,00 m2", "12,63", "EUR", "101.040,00"],
            ["", "Summe 106. 1. 1 Sauberkeitsschichten", "", "EUR", "221.286,30"],
            ["106. 1. 2", "Trennschichten / Trennlagen", "", "", ""],
        ]
    }]
    result = parse_lv_tables(tables)
    # Summenzeile darf nicht dabei sein
    ozs = [p["oz"] for p in result]
    assert "106.1.1.10" in ozs
    assert not any("summe" in (p.get("kurztext") or "").lower() for p in result)


# --- Vollstaendige Tabelle (FLI-Format) ---

def test_fli_tabelle_komplett():
    tables = [{
        "header": ["Ordnungszahl", "Menge Einheit", "Einheitspreis", "Währung", "Gesamtpreis"],
        "rows": [
            ["106", "Rohbauarbeiten Technische", "", "", ""],
            ["", "Vorbemerkungen", "", "", ""],
            ["106. 1", "Stahlbetonarbeiten", "", "", ""],
            ["106. 1. 1", "Sauberkeitsschichten", "", "", ""],
            ["106. 1. 1. 10", "8.000,00 m2", "12,63", "EUR", "101.040,00"],
            ["106. 1. 1. 20", "8.000,00 m2 Sauberkeitsschicht C 12/15, d = 5 cm", "12,63", "EUR", "101.040,00"],
            ["106. 1. 1. 30", "150,00 m3 Fundament, Abtreppung, C 8/10", "93,09", "EUR", "13.963,50"],
            ["106. 1. 1. 40", "120,00 m2 Schalung für Fundamentauffüllungen,", "43,69", "EUR", "5.242,80"],
            ["", "Summe 106. 1. 1 Sauberkeitsschichten", "", "EUR", "221.286,30"],
        ]
    }]
    result = parse_lv_tables(tables)

    # Titel
    titel = [p for p in result if p["ist_titel"]]
    assert len(titel) >= 3  # 106, 106.1, 106.1.1

    # Positionen
    positionen = [p for p in result if not p["ist_titel"] and p["menge"] is not None]
    assert len(positionen) == 4

    # Erste Position: nur Menge, keine Beschreibung
    p1 = next(p for p in positionen if p["oz"] == "106.1.1.10")
    assert p1["menge"] == Decimal("8000.00")
    assert p1["einheit"] == "m2"
    assert p1["einheitspreis"] == Decimal("12.63")
    assert p1["gesamtpreis"] == Decimal("101040.00")

    # Zweite Position: Menge + Beschreibung
    p2 = next(p for p in positionen if p["oz"] == "106.1.1.20")
    assert p2["menge"] == Decimal("8000.00")
    assert p2["einheit"] == "m2"
    assert "Sauberkeitsschicht" in p2["kurztext"]

    # Keine Summenzeile
    assert not any("Summe" in (p.get("kurztext") or "") for p in result)

    # OZ normalisiert
    assert all("  " not in (p["oz"] or "") for p in result)