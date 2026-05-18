"""BauPilot — Middleware fuer Tenant-Resolution und Audit-Logging.
Liest den Mandanten aus dem Request-Header X-Tenant-Slug und
setzt den search_path fuer die aktuelle Transaktion.
"""
import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
logger = structlog.get_logger()
TENANT_HEADER = "X-Tenant-Slug"
REQUEST_ID_HEADER = "X-Request-ID"
# Pfade, die keinen Tenant-Header benoetigen.
# Wenn ein neues Backend-Modul angelegt wird, MUSS hier sein Pfad-Praefix
# eingetragen werden — sonst lehnt die Middleware alle Requests mit HTTP 400
# ab, bevor sie den Router erreichen (war urspruengliches Verhalten in
# §B-003, Schema-per-Tenant mit benutzer_projekt_rollen.mandant_slug als
# eigentlicher Identitaetsquelle — der Header wird derzeit nicht aktiv genutzt).
TENANT_EXEMPT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}
TENANT_EXEMPT_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/aufgaben",
    "/api/v1/vorgaenge",
    "/api/v1/kontakte",
    "/api/v1/dokumente",
    "/api/v1/lv",
    "/api/v1/nachtraege",
    "/api/v1/behinderungen",    # E6, AP 2.2a
    "/api/v1/bedenken",         # E7, AP 2.2b
    "/api/v1/maengel",          # E8, AP 2.2c
    "/api/v1/benachrichtigungen",  # E10, B-012
    "/api/v1/tags",             # E11, B-013
)
class TenantMiddleware(BaseHTTPMiddleware):
    """Extrahiert den Mandanten-Slug aus dem Request-Header."""
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path in TENANT_EXEMPT_PATHS or any(path.startswith(p) for p in TENANT_EXEMPT_PREFIXES):
            return await call_next(request)
        tenant_slug = request.headers.get(TENANT_HEADER)
        if not tenant_slug:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Header {TENANT_HEADER} fehlt."},
            )
        # Tenant-Slug im Request-State speichern
        request.state.tenant_slug = tenant_slug
        return await call_next(request)
class AuditLogMiddleware(BaseHTTPMiddleware):
    """Strukturiertes Logging fuer jeden Request (G2 Revisionssicherheit)."""
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
            tenant=getattr(request.state, "tenant_slug", None),
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
