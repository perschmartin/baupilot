"""BauPilot — Bedenkenanzeigen-Workflow (AP 2.2b).

6-Schritte-Workflow nach VOB/B §4 Abs. 3 (Bedenkenpflicht des AN). Analog
zum Behinderungs-Modul, zusaetzlich mit Zuordnung zu LV-Position und
Gewaehrleistungsfrist (`gewaehrleistung_bis`).

Schritte: 1=Erfassung, 2=Pruefung, 3=Anerkennung/Rueckweisung,
4=Schriftverkehr, 5=ggf. erneute Pruefung, 6=Abmeldung GU.
"""

from bedenken.router import router as bedenken_router

__all__ = ["bedenken_router"]
