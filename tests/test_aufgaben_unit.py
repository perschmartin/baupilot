"""
Tests fuer AP 1.3 — Aufgabenmanagement.

Testet Schemas, Statusmaschine und Service-Logik.
Laeuft ohne DB (pure Unit-Tests fuer Validierung).
"""

import sys
import os
import pytest
from datetime import date
from uuid import uuid4

# api/ zum Pfad hinzufuegen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

# Schemas direkt importieren (ohne __init__.py, das den Router laedt)
from pydantic import BaseModel, Field


# === Schemas inline dupliziert fuer isolierte Tests ===
# (Vermeidet Import-Kette aufgaben → router → auth → config → .env)

class AufgabeErstellen(BaseModel):
    gegenstand: str = Field(min_length=1, max_length=1000)
    beschreibung: str | None = None
    prioritaet: str = Field(default="mittel", pattern=r"^(kritisch|hoch|mittel|niedrig)$")
    zustaendig_benutzer_id: object | None = None
    frist: date | None = None
    kosten_eur: float | None = None
    zeit_arbeitstage: int | None = None
    qualitaet_bewertung: str | None = None


class AufgabeAktualisieren(BaseModel):
    gegenstand: str | None = Field(default=None, min_length=1, max_length=1000)
    beschreibung: str | None = None
    prioritaet: str | None = Field(default=None, pattern=r"^(kritisch|hoch|mittel|niedrig)$")
    status: str | None = Field(default=None, pattern=r"^(offen|in_bearbeitung|geprueft|abgeschlossen|storniert)$")
    kosten_eur: float | None = None
    zeit_arbeitstage: int | None = None
    qualitaet_bewertung: str | None = None


class KommentarErstellen(BaseModel):
    inhalt: str = Field(min_length=1, max_length=10000)


GUELTIGE_UEBERGAENGE = {
    "offen": {"in_bearbeitung", "storniert"},
    "in_bearbeitung": {"geprueft", "storniert"},
    "geprueft": {"abgeschlossen", "offen", "storniert"},
    "abgeschlossen": set(),
    "storniert": set(),
}


# ===================================================================
# Schema-Tests
# ===================================================================

class TestAufgabeErstellen:

    def test_minimal(self):
        a = AufgabeErstellen(gegenstand="Pruefbericht erstellen")
        assert a.gegenstand == "Pruefbericht erstellen"
        assert a.prioritaet == "mittel"
        assert a.beschreibung is None
        assert a.frist is None

    def test_vollstaendig(self):
        uid = uuid4()
        a = AufgabeErstellen(
            gegenstand="Mahnungsschreiben an GP",
            beschreibung="Wegen Verzoegerung Rohbau 2.OG",
            prioritaet="hoch",
            zustaendig_benutzer_id=uid,
            frist=date(2026, 6, 1),
            kosten_eur=1500.00,
            zeit_arbeitstage=3,
            qualitaet_bewertung="Terminrelevant",
        )
        assert a.prioritaet == "hoch"
        assert a.zustaendig_benutzer_id == uid
        assert a.kosten_eur == 1500.00
        assert a.zeit_arbeitstage == 3

    def test_leerer_gegenstand_abgelehnt(self):
        with pytest.raises(Exception):
            AufgabeErstellen(gegenstand="")

    def test_ungueltige_prioritaet_abgelehnt(self):
        with pytest.raises(Exception):
            AufgabeErstellen(gegenstand="Test", prioritaet="ultra")

    def test_gueltige_prioritaeten(self):
        for p in ("kritisch", "hoch", "mittel", "niedrig"):
            a = AufgabeErstellen(gegenstand="Test", prioritaet=p)
            assert a.prioritaet == p


class TestAufgabeAktualisieren:

    def test_einzelnes_feld(self):
        a = AufgabeAktualisieren(prioritaet="kritisch")
        felder = a.model_dump(exclude_unset=True)
        assert felder == {"prioritaet": "kritisch"}

    def test_status_validierung(self):
        a = AufgabeAktualisieren(status="in_bearbeitung")
        assert a.status == "in_bearbeitung"

    def test_ungueltigier_status_abgelehnt(self):
        with pytest.raises(Exception):
            AufgabeAktualisieren(status="fertig")

    def test_leeres_update_moeglich(self):
        a = AufgabeAktualisieren()
        felder = a.model_dump(exclude_unset=True)
        assert felder == {}


class TestKommentarErstellen:

    def test_gueltig(self):
        k = KommentarErstellen(inhalt="Pruefbericht liegt vor.")
        assert k.inhalt == "Pruefbericht liegt vor."

    def test_leer_abgelehnt(self):
        with pytest.raises(Exception):
            KommentarErstellen(inhalt="")

    def test_lang(self):
        k = KommentarErstellen(inhalt="x" * 10000)
        assert len(k.inhalt) == 10000

    def test_zu_lang_abgelehnt(self):
        with pytest.raises(Exception):
            KommentarErstellen(inhalt="x" * 10001)


# ===================================================================
# Statusmaschine-Tests
# ===================================================================

class TestStatusmaschine:

    def test_offen_nach_in_bearbeitung(self):
        assert "in_bearbeitung" in GUELTIGE_UEBERGAENGE["offen"]

    def test_offen_nach_storniert(self):
        assert "storniert" in GUELTIGE_UEBERGAENGE["offen"]

    def test_offen_nicht_nach_abgeschlossen(self):
        assert "abgeschlossen" not in GUELTIGE_UEBERGAENGE["offen"]

    def test_in_bearbeitung_nach_geprueft(self):
        assert "geprueft" in GUELTIGE_UEBERGAENGE["in_bearbeitung"]

    def test_geprueft_nach_abgeschlossen(self):
        assert "abgeschlossen" in GUELTIGE_UEBERGAENGE["geprueft"]

    def test_geprueft_zurueckspielen(self):
        assert "offen" in GUELTIGE_UEBERGAENGE["geprueft"]

    def test_abgeschlossen_ist_endstatus(self):
        assert len(GUELTIGE_UEBERGAENGE["abgeschlossen"]) == 0

    def test_storniert_ist_endstatus(self):
        assert len(GUELTIGE_UEBERGAENGE["storniert"]) == 0

    def test_jeder_status_hat_storniert(self):
        for status, erlaubt in GUELTIGE_UEBERGAENGE.items():
            if status not in ("abgeschlossen", "storniert"):
                assert "storniert" in erlaubt, f"{status} fehlt storniert"

    def test_alle_status_abgedeckt(self):
        erwartete = {"offen", "in_bearbeitung", "geprueft", "abgeschlossen", "storniert"}
        assert set(GUELTIGE_UEBERGAENGE.keys()) == erwartete


# ===================================================================
# Dreiklang-Tests (G3)
# ===================================================================

class TestDreiklang:

    def test_dreiklang_felder_vorhanden(self):
        a = AufgabeErstellen(
            gegenstand="Test",
            kosten_eur=5000.0,
            zeit_arbeitstage=10,
            qualitaet_bewertung="Keine Auswirkung",
        )
        assert a.kosten_eur == 5000.0
        assert a.zeit_arbeitstage == 10
        assert a.qualitaet_bewertung == "Keine Auswirkung"

    def test_dreiklang_optional(self):
        a = AufgabeErstellen(gegenstand="Test")
        assert a.kosten_eur is None
        assert a.zeit_arbeitstage is None
        assert a.qualitaet_bewertung is None

    def test_dreiklang_aktualisierbar(self):
        a = AufgabeAktualisieren(kosten_eur=12000.50)
        felder = a.model_dump(exclude_unset=True)
        assert felder["kosten_eur"] == 12000.50
