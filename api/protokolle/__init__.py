"""BauPilot — Protokollgenerierung (AP 2.5, Roadmap E12).

Erzeugt Word-Protokolle (.docx) aus Vorgangs-Daten. Heute fuer Nachtraege —
spaetere Etappen koennen den Renderer auf Behinderungen, Bedenken und
Maengel ausweiten.

Der Service ist bewusst eine reine Render-Funktion ohne DB-Zugriff. Der
aufrufende Router laedt die Daten und uebergibt das Dict.
"""

from protokolle.service import render_nachtrag_protokoll

__all__ = ["render_nachtrag_protokoll"]
