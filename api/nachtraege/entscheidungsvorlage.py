"""
Entscheidungsvorlage — KI-gestuetzte Generierung faktenbasierter Vorlagen (Schritt 4).

Verwendet LiteLLM → Ollama → Qwen 2.5 32B.
G1: Sachliche Neutralitaet, keine Wertungen.
G2: Lokale Verarbeitung, keine externen APIs.
B-002: Ergebnis erfordert menschliche Freigabe.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings

logger = logging.getLogger(__name__)

# LiteLLM-Endpunkt (intern ueber Docker-Netzwerk)
LITELLM_BASE = f"http://{settings.litellm_host}:{settings.litellm_port}"

# System-Prompt (G1-konform, optimiert 09.05.2026)
SYSTEM_PROMPT = """Du bist der BauPilot-Assistent fuer Nachtragspruefungen im oeffentlichen Hochbau (VOB/B).
Deine Aufgabe ist es, eine faktenbasierte Entscheidungsvorlage fuer die Projektleitung zu erstellen.

STRIKTE REGELN:
- Nur Fakten aus dem bereitgestellten Kontext verwenden. Nichts erfinden.
- Keine Schuldzuweisungen, Wertungen oder Spekulationen zu Projektbeteiligten (G1).
- Jede Aussage mit Quellenangabe (LV-Nummer, OZ-Position, Datum, Betrag).
- Dreiklang IMMER ausfuellen: Kosten (EUR netto), Zeit (Arbeitstage), Qualitaet.
- Sprache: Deutsch, sachlich, behoerdengerecht, praezise.

VERBOTEN:
- Markdown-Listen (keine Aufzaehlungszeichen, keine Spiegelstriche, keine nummerierten Listen).
- Den Begriff "Liefervertrag" — korrekt ist "Werkvertrag" (VOB/B, BGB §631 ff.).
- Wertende Adjektive wie "ueberteuert", "unangemessen", "unverschaemt".
- Spekulationen ueber Motive oder Absichten der Vertragspartner.

FORMAT — Genau drei Abschnitte, jeweils als Fliesstext:
1. Abschnitt beginnt mit der Zeile: SACHVERHALT
2. Abschnitt beginnt mit der Zeile: PRUEFERGEBNIS
3. Abschnitt beginnt mit der Zeile: BAUPILOT-EINSCHAETZUNG

Jeder Abschnitt enthaelt den Dreiklang (Kosten, Zeit, Qualitaet) soweit die Datenlage es hergibt.
Der letzte Abschnitt schliesst mit dem Satz: "Die endgueltige Entscheidung liegt bei der Projektleitung."
"""


class EntscheidungsvorlageService:
    """Generiert und verwaltet Entscheidungsvorlagen."""

    def __init__(self, db: Session, mandant_slug: str = ""):
        self.db = db
        self.mandant_slug = mandant_slug

    def _commit(self):
        """Commit mit search_path-Wiederherstellung."""
        self.db.commit()
        if self.mandant_slug:
            self.db.execute(
                text(f"SET search_path TO tenant_{self.mandant_slug}, shared, public")
            )

    def generiere(
        self,
        vorgang_id: UUID,
        erstellt_von_id: str,
        lv_abgleich: dict[str, Any] | None = None,
        kostenabgleich: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Entscheidungsvorlage generieren.
        Sammelt Kontext aus Nachtrag + Schritt 2+3, ruft LLM auf, speichert.
        """

        # Nachtrag laden
        vorgang = self.db.execute(
            text("""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung,
                       v.betrag_gefordert, v.zeitauswirkung_tage,
                       v.qualitaetsauswirkung, v.kostengruppe_din276,
                       f.name AS firma_name
                FROM vorgaenge v
                LEFT JOIN firmen f ON f.id = v.verantwortlich_firma_id
                WHERE v.id = :id AND v.typ = 'nachtrag' AND NOT v.geloescht
            """),
            {"id": str(vorgang_id)},
        ).mappings().first()

        if not vorgang:
            raise ValueError("Nachtrag nicht gefunden.")

        # Kontext zusammenstellen
        kontext = self._baue_kontext(dict(vorgang), lv_abgleich, kostenabgleich)

        # LLM aufrufen
        vorlage_text = self._llm_aufruf(kontext)

        # Naechste Version ermitteln
        version_row = self.db.execute(
            text("""
                SELECT COALESCE(MAX(version), 0) + 1 AS v
                FROM entscheidungsvorlagen WHERE vorgang_id = :vid
            """),
            {"vid": str(vorgang_id)},
        ).mappings().first()
        version = version_row["v"]

        # Basisdaten zusammenstellen
        basisdaten = {
            "lv_abgleich": lv_abgleich,
            "kostenabgleich": kostenabgleich,
            "nachtrag": {
                "nummer": vorgang["nummer"],
                "gegenstand": vorgang["gegenstand"],
                "betrag_gefordert": float(vorgang["betrag_gefordert"]) if vorgang["betrag_gefordert"] else None,
                "firma": vorgang["firma_name"],
            },
        }

        # Speichern
        row = self.db.execute(
            text("""
                INSERT INTO entscheidungsvorlagen (
                    vorgang_id, version, vorlage_text, basisdaten,
                    generiert_von, erstellt_von
                ) VALUES (
                    :vid, :version, :text, CAST(:basisdaten AS jsonb),
                    'baupilot', :erstellt_von
                )
                RETURNING id, vorgang_id, version, vorlage_text, basisdaten,
                          freigegeben, freigegeben_von, freigegeben_am,
                          erstellt_am, erstellt_von
            """),
            {
                "vid": str(vorgang_id),
                "version": version,
                "text": vorlage_text,
                "basisdaten": json.dumps(basisdaten, ensure_ascii=False, default=str),
                "erstellt_von": erstellt_von_id,
            },
        ).mappings().first()

        self._commit()

        result = dict(row)
        result["hinweis"] = "Entwurf — muss vor Verwendung freigegeben werden"
        return result

    def freigeben(
        self,
        vorlage_id: UUID,
        freigegeben_von_id: str,
    ) -> dict[str, Any]:
        """Entscheidungsvorlage freigeben (nur PL/Admin)."""

        row = self.db.execute(
            text("""
                UPDATE entscheidungsvorlagen SET
                    freigegeben = TRUE,
                    freigegeben_von = :von,
                    freigegeben_am = NOW()
                WHERE id = :id AND NOT freigegeben
                RETURNING id, vorgang_id, version, vorlage_text, basisdaten,
                          freigegeben, freigegeben_von, freigegeben_am,
                          erstellt_am, erstellt_von
            """),
            {"id": str(vorlage_id), "von": freigegeben_von_id},
        ).mappings().first()

        if not row:
            raise ValueError("Vorlage nicht gefunden oder bereits freigegeben.")

        self._commit()
        return dict(row)

    def lade_vorlagen(self, vorgang_id: UUID) -> list[dict[str, Any]]:
        """Alle Vorlagen eines Nachtrags laden."""
        rows = self.db.execute(
            text("""
                SELECT id, vorgang_id, version, vorlage_text, basisdaten,
                       freigegeben, freigegeben_von, freigegeben_am,
                       erstellt_am, erstellt_von
                FROM entscheidungsvorlagen
                WHERE vorgang_id = :vid
                ORDER BY version DESC
            """),
            {"vid": str(vorgang_id)},
        ).mappings().all()

        return [dict(r) for r in rows]

    def _baue_kontext(
        self,
        vorgang: dict[str, Any],
        lv_abgleich: dict[str, Any] | None,
        kostenabgleich: dict[str, Any] | None,
    ) -> str:
        """Kontext-String fuer den LLM-Prompt zusammenbauen."""

        teile = [
            f"NACHTRAG: {vorgang.get('nummer', '?')}",
            f"Gegenstand: {vorgang.get('gegenstand', '?')}",
        ]

        if vorgang.get("beschreibung"):
            teile.append(f"Beschreibung: {vorgang['beschreibung']}")
        if vorgang.get("betrag_gefordert"):
            teile.append(f"Geforderter Betrag: {vorgang['betrag_gefordert']:.2f} EUR netto")
        if vorgang.get("zeitauswirkung_tage"):
            teile.append(f"Zeitauswirkung: {vorgang['zeitauswirkung_tage']} Arbeitstage")
        if vorgang.get("qualitaetsauswirkung"):
            teile.append(f"Qualitaetsauswirkung: {vorgang['qualitaetsauswirkung']}")
        if vorgang.get("firma_name"):
            teile.append(f"Ausfuehrende Firma: {vorgang['firma_name']}")
        if vorgang.get("kostengruppe_din276"):
            teile.append(f"Kostengruppe DIN 276: {vorgang['kostengruppe_din276']}")

        if lv_abgleich and lv_abgleich.get("treffer"):
            teile.append("\nLV-ABGLEICH:")
            for t in lv_abgleich["treffer"][:5]:
                teile.append(
                    f"  - LV {t.get('lv_nummer', '?')} Pos. {t.get('oz', '?')}: "
                    f"{t.get('kurztext', '')} "
                    f"(EP: {t.get('einheitspreis', '?')} EUR/{t.get('einheit', '?')}, "
                    f"Relevanz: {t.get('relevanz', 0):.2f})"
                )

        if kostenabgleich and kostenabgleich.get("vergleiche"):
            teile.append(f"\nKOSTENABGLEICH (Regionalfaktor: {kostenabgleich.get('bki_regionalfaktor', '?')}):")
            for v in kostenabgleich["vergleiche"][:5]:
                teile.append(
                    f"  - {v.get('quelle', '?')}: {v.get('bezeichnung', '')} "
                    f"({v.get('referenzpreis_regionalisiert') or v.get('referenzpreis_netto', '?')} EUR, "
                    f"Abweichung: {v.get('abweichung_prozent', '?')}%, "
                    f"Bewertung: {v.get('bewertung', '?')})"
                )
            teile.append(f"Gesamtbewertung: {kostenabgleich.get('gesamtbewertung', '?')}")

        return "\n".join(teile)

    def _llm_aufruf(self, kontext: str) -> str:
        """LLM ueber LiteLLM aufrufen. Fallback auf Platzhalter bei Fehler."""

        prompt = f"""Erstelle eine Entscheidungsvorlage fuer folgenden Nachtrag.

KONTEXT:
{kontext}

Schreibe die Vorlage als strukturierten Fliesstext mit genau drei Abschnitten.
Keine Aufzaehlungen, keine Spiegelstriche, keine nummerierten Listen.

SACHVERHALT
Beschreibe in zusammenhaengendem Fliesstext: Was wird gefordert, von wem, in welcher Hoehe, mit welcher Zeitauswirkung und welchen Qualitaetsfolgen. Verweise auf die betroffene LV-Nummer und Kostengruppe.

PRUEFERGEBNIS
Beschreibe in zusammenhaengendem Fliesstext: Ergebnis des LV-Abgleichs (welche Positionen wurden gefunden, wie hoch ist die Uebereinstimmung), Ergebnis des Kostenabgleichs (Referenzpreise, Abweichungen in Prozent, Bewertung). Benenne Auffaelligkeiten mit Quellenangabe.

BAUPILOT-EINSCHAETZUNG
Beschreibe in zusammenhaengendem Fliesstext: Zusammenfassende Bewertung des Dreiklangs (Kosten, Zeit, Qualitaet). Empfehlung fuer das weitere Vorgehen (z.B. detaillierte Kostenberechnung anfordern, Teilung der Forderung, Alternativloesungen). Schliesse mit: "Die endgueltige Entscheidung liegt bei der Projektleitung."
"""

        try:
            response = httpx.post(
                f"{LITELLM_BASE}/v1/chat/completions",
                json={
                    "model": "qwen-32b",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"LLM-Aufruf fehlgeschlagen: {e}")
            # Fallback-Vorlage
            return (
                f"[ENTWURF — LLM nicht verfuegbar, manuelle Bearbeitung erforderlich]\n\n"
                f"SACHVERHALT:\n{kontext}\n\n"
                f"PRUEFERGEBNIS:\nAutomatische Pruefung konnte nicht durchgefuehrt werden.\n\n"
                f"EMPFEHLUNG:\nManuelle Pruefung durch Projektleitung erforderlich."
            )
