"""BauPilot — Benachrichtigungssystem (B-012, Roadmap E10).

In-App-Benachrichtigungen (B-012 Variante A: Pflicht-Primaerweg) ueber die
in Migration 008 angelegten Tabellen `benachrichtigungen` und
`benachrichtigungs_regeln`.

Diese Implementierung deckt Variante A ab. Variante B (SMTP-Adapter) ist als
Stub vorbereitet, aber per Default inaktiv. Variante C (Export-Endpoint) folgt
spaeter, sobald die Adoption stabil ist.

Trigger werden von anderen Modulen (z.B. aufgaben.service) ueber den
BenachrichtigungsService.erstelle()-Helper aufgerufen — keine impliziten
Hooks, alle Trigger sind explizit im Code lokalisiert.
"""

from benachrichtigungen.router import router as benachrichtigungen_router
from benachrichtigungen.service import BenachrichtigungsService

__all__ = ["benachrichtigungen_router", "BenachrichtigungsService"]
