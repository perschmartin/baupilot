"""
BauPilot Auth-System.

Integriert bewährte Patterns aus dem 2FA-Toolkit (familienstiftung.software)
mit BauPilot-spezifischer Architektur (JWT, Multi-Tenant, Air-Gap).
"""

from auth.router import router as auth_router

__all__ = ["auth_router"]
