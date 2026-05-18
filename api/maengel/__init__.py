"""BauPilot — Mangelanzeigen-Workflow (AP 2.2c).

5-Schritte-Workflow nach VOB/B §13 (Maengelanspruch). Strukturell aehnlich
zu Behinderungen und Bedenken, aber:
  - Nur 5 Schritte: 1=Erfassung, 2=Mangelschreiben, 3=Schriftverkehr,
    4=Abmeldung GU/GP, 5=Bestaetigung Bauherr
  - mangelart-Enum entscheidet Verantwortung (Ausfuehrung → GU, Planung → GP)
  - Kostenuntergliederung in nachtragsfolge_eur, folgekosten_betrieb_eur, minderkosten_eur
  - verlaengerung_monate fuer Gewaehrleistungsverlaengerung
"""

from maengel.router import router as maengel_router

__all__ = ["maengel_router"]
