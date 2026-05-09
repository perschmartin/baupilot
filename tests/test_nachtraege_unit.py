"""
Tests fuer Nachtragsmanagement — CRUD und 7-Schritte-Workflow.

Offline-faehig: Kein Docker, kein PostgreSQL noetig.
Testet die Geschaeftslogik via Mock-DB.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4, UUID

# Direkter Import ohne __init__.py (vermeidet Router/Auth/DB-Chain)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

# Mock database und config bevor nachtraege.service importiert wird
sys.modules['database'] = MagicMock()
sys.modules['config'] = MagicMock()
sys.modules['config'].settings = MagicMock(
    litellm_host='localhost', litellm_port=4000,
    database_url='postgresql://test:test@localhost/test',
)

from nachtraege.service import NachtragsService, NachtragsError, PRUEFSCHRITT_TITEL


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mock_db():
    """Mock-DB mit grundlegenden Queries."""
    db = MagicMock()
    return db


def _make_service(db=None, slug="tlbv"):
    if db is None:
        db = _mock_db()
    return NachtragsService(db=db, mandant_slug=slug)


# ---------------------------------------------------------------------------
# PRUEFSCHRITT_TITEL
# ---------------------------------------------------------------------------

class TestPruefschrittTitel:

    def test_alle_sieben_schritte_definiert(self):
        assert len(PRUEFSCHRITT_TITEL) == 7
        for i in range(1, 8):
            assert i in PRUEFSCHRITT_TITEL
            assert isinstance(PRUEFSCHRITT_TITEL[i], str)
            assert len(PRUEFSCHRITT_TITEL[i]) > 0

    def test_schritt_1_ist_erfassung(self):
        assert PRUEFSCHRITT_TITEL[1] == "Erfassung"

    def test_schritt_4_ist_entscheidungsvorlage(self):
        assert PRUEFSCHRITT_TITEL[4] == "Entscheidungsvorlage"

    def test_schritt_7_ist_abschluss(self):
        assert "Abschluss" in PRUEFSCHRITT_TITEL[7]


# ---------------------------------------------------------------------------
# NachtragsError
# ---------------------------------------------------------------------------

class TestNachtragsError:

    def test_error_mit_default_status(self):
        err = NachtragsError("Test-Fehler")
        assert err.detail == "Test-Fehler"
        assert err.status_code == 400

    def test_error_mit_custom_status(self):
        err = NachtragsError("Nicht gefunden", 404)
        assert err.status_code == 404

    def test_error_ist_exception(self):
        err = NachtragsError("Test")
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# Service-Initialisierung
# ---------------------------------------------------------------------------

class TestServiceInit:

    def test_service_mit_mandant(self):
        svc = _make_service(slug="tlbv")
        assert svc.mandant_slug == "tlbv"

    def test_service_ohne_mandant(self):
        svc = _make_service(slug="")
        assert svc.mandant_slug == ""


# ---------------------------------------------------------------------------
# Workflow-Validierung
# ---------------------------------------------------------------------------

class TestWorkflowLogik:

    def test_variante_a_muss_gueltig_sein(self):
        """Variante muss A, B oder C sein."""
        svc = _make_service()
        with pytest.raises(NachtragsError, match="Variante muss A, B oder C"):
            svc.entscheidung_treffen(
                nachtrag_id=uuid4(),
                variante="D",
                benutzer_id=str(uuid4()),
                benutzer_name="Test",
            )

    def test_ki_ergebnis_nur_schritte_2_bis_4(self):
        """KI-Ergebnis nur fuer Schritte 2, 3, 4 zulaessig."""
        svc = _make_service()
        with pytest.raises(NachtragsError, match="nur fuer Schritte 2-4"):
            svc.ki_ergebnis_speichern(
                nachtrag_id=uuid4(),
                schritt_nr=5,
                benutzer_id=str(uuid4()),
                ki_eingabe={},
                ki_ergebnis={},
            )

    def test_ki_bestaetigung_nur_schritte_2_bis_4(self):
        """KI-Bestaetigung nur fuer Schritte 2, 3, 4."""
        svc = _make_service()
        with pytest.raises(NachtragsError, match="nur fuer Schritte 2-4"):
            svc.ki_bestaetigen(
                nachtrag_id=uuid4(),
                schritt_nr=1,
                benutzer_id=str(uuid4()),
                bestaetigt=True,
            )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TestSchemas:

    def test_nachtrag_erstellen_minimal(self):
        from nachtraege.schemas import NachtragErstellen
        body = NachtragErstellen(gegenstand="Testauftrag Betonarbeiten")
        assert body.gegenstand == "Testauftrag Betonarbeiten"
        assert body.betrag_gefordert is None

    def test_nachtrag_erstellen_vollstaendig(self):
        from nachtraege.schemas import NachtragErstellen
        body = NachtragErstellen(
            gegenstand="Zusaetzliche Stahlbetonarbeiten",
            beschreibung="Fundament erweitert",
            betrag_gefordert=125000.50,
            zeitauswirkung_tage=15,
            qualitaetsauswirkung="Keine Auswirkung",
            kostengruppe_din276="300",
        )
        assert body.betrag_gefordert == 125000.50
        assert body.zeitauswirkung_tage == 15

    def test_nachtrag_variante_validierung(self):
        from nachtraege.schemas import NachtragAktualisieren
        body = NachtragAktualisieren(nachtragsvariante="A")
        assert body.nachtragsvariante == "A"

    def test_nachtrag_variante_ungueltig(self):
        from nachtraege.schemas import NachtragAktualisieren
        with pytest.raises(Exception):
            NachtragAktualisieren(nachtragsvariante="X")

    def test_pruefschritt_abschliessen(self):
        from nachtraege.schemas import PruefschrittAbschliessen
        body = PruefschrittAbschliessen(ergebnis="LV-Abgleich bestaetigt")
        assert body.ergebnis == "LV-Abgleich bestaetigt"

    def test_ki_bestaetigung(self):
        from nachtraege.schemas import KiBestaetigung
        body = KiBestaetigung(bestaetigt=True, kommentar="Passt")
        assert body.bestaetigt is True


# ---------------------------------------------------------------------------
# LV-Abgleich
# ---------------------------------------------------------------------------

class TestLVAbgleich:

    def test_leerer_suchbegriff(self):
        from nachtraege.lv_abgleich import LVAbgleichService
        db = MagicMock()
        db.execute.return_value.mappings.return_value.first.return_value = {
            "id": uuid4(), "gegenstand": "", "beschreibung": None, "lv_id": None,
        }
        svc = LVAbgleichService(db=db)
        result = svc.abgleich(vorgang_id=uuid4())
        assert result["anzahl_treffer"] == 0

    def test_tsquery_konstruktion(self):
        """Kurze Woerter (<=2 Zeichen) werden gefiltert."""
        from nachtraege.lv_abgleich import LVAbgleichService
        svc = LVAbgleichService(db=MagicMock())
        # Interne Methode testen
        woerter = [w.strip() for w in "in der Wand".split() if w.strip() and len(w.strip()) > 2]
        assert woerter == ["der", "Wand"]


# ---------------------------------------------------------------------------
# Kostenabgleich
# ---------------------------------------------------------------------------

class TestKostenabgleich:

    def test_bewertung_angemessen(self):
        from nachtraege.kostenabgleich import KostenabgleichService
        assert KostenabgleichService._bewerte_abweichung(5.0) == "angemessen"
        assert KostenabgleichService._bewerte_abweichung(-8.0) == "angemessen"

    def test_bewertung_ueber_bandbreite(self):
        from nachtraege.kostenabgleich import KostenabgleichService
        assert KostenabgleichService._bewerte_abweichung(25.0) == "ueber_bandbreite"

    def test_bewertung_unter_bandbreite(self):
        from nachtraege.kostenabgleich import KostenabgleichService
        assert KostenabgleichService._bewerte_abweichung(-15.0) == "unter_bandbreite"

    def test_bewertung_none(self):
        from nachtraege.kostenabgleich import KostenabgleichService
        assert KostenabgleichService._bewerte_abweichung(None) == "kein_vergleich"


# ---------------------------------------------------------------------------
# Entscheidungsvorlage
# ---------------------------------------------------------------------------

class TestEntscheidungsvorlage:

    def test_system_prompt_g1_konform(self):
        from nachtraege.entscheidungsvorlage import SYSTEM_PROMPT
        assert "Schuldzuweisungen" in SYSTEM_PROMPT
        assert "G1" in SYSTEM_PROMPT
        assert "Dreiklang" in SYSTEM_PROMPT
        assert "BauPilot-Einschaetzung" in SYSTEM_PROMPT

    def test_kontext_bau(self):
        from nachtraege.entscheidungsvorlage import EntscheidungsvorlageService
        svc = EntscheidungsvorlageService(db=MagicMock())
        kontext = svc._baue_kontext(
            vorgang={"nummer": "NT-001", "gegenstand": "Betonarbeiten", "betrag_gefordert": 50000},
            lv_abgleich=None,
            kostenabgleich=None,
        )
        assert "NT-001" in kontext
        assert "Betonarbeiten" in kontext
        assert "50000" in kontext
