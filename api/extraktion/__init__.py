"""BauPilot — LLM-Daten-Extraktion aus Stoerungs-PDFs (E13b, AP 2.6 erste Stufe).

Liest verknuepfte PDFs zu einem Vorgang aus MinIO, extrahiert Text mit
pdfplumber und ruft Qwen 2.5 32B via LiteLLM auf, um strukturierte Felder
zu erkennen (Beschreibung, verantwortliche Firma, Datum, Auswirkungen).

Gilt fuer Behinderungen, Bedenken und Maengel — Nachtraege bekommen
spaeter einen eigenen, an die 7-Schritte-Pipeline angepassten Pfad.

B-002: LLM-Ergebnis erfordert menschliche Bestaetigung. Bei Bestaetigung
wandert das Ergebnis in die `vorgaenge`-Spalten.
"""

from extraktion.router import router as extraktion_router

__all__ = ["extraktion_router"]
