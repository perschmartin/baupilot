"""BauPilot — Behinderungsanzeigen-Workflow (AP 2.2a).

6-Schritte-Workflow nach VOB/B §6 (Behinderung). Analog zum Nachtragsmodul
strukturiert, aber ohne LV-Abgleich/Kostenabgleich/LLM-Entscheidungsvorlage —
diese sind fuer Behinderungsanzeigen fachlich nicht erforderlich.

Schritte: 1=Erfassung, 2=Pruefung, 3=Anerkennung/Rueckweisung,
4=Schriftverkehr, 5=ggf. erneute Pruefung, 6=Abmeldung GU.
"""

from behinderungen.router import router as behinderungen_router

__all__ = ["behinderungen_router"]
