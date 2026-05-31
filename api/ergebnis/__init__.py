"""BauPilot — Ergebnis-Modul (Saeule 3 vorgezogen).

Liefert die Datenbasis fuer die Ergebnis-Seite im Frontend: eine
flat-Vorgangstabelle mit aufgeloestem Verursacher + Bauteil + Dreiklang
(Q/Z/K), den (vorlaeufigen) Nullterminplan, und aggregierte Kennzahlen.

Hintergrund: Konzept v0.4 §9 nennt diese Funktionen unter Phase 3:
  - AP 3.2 Soll-Ist-Darstellung mit Stoerungsmarkern (Gantt)
  - AP 3.4 Verantwortlichkeitsmatrix (Sankey/Heatmap)
  - AP 3.5 Berichtserstellung (Wasserfall/Onepager)

Bis der Asta-X83-Parser kommt (AP 3.1), wird der Nullterminplan
als JSON-Seed gepflegt — siehe data/nullterminplan.json.
"""

from ergebnis.router import router as ergebnis_router

__all__ = ["ergebnis_router"]
