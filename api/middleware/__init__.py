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
# Pfade, die keinen Tenant benoetigen
TENANT_EXEMPT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}
class TenantMiddleware(BaseHTTPMiddleware):
    """Extrahiert den Mandanten-Slug aus dem Request-Header."""
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path in TENANT_EXEMPT_PATHS or path.startswith("/api/v1/auth") or path.startswith("/api/v1/aufgaben") or path.startswith("/api/v1/vorgaenge") or path.startswith("/api/v1/kontakte") or path.startswith("/api/v1/dokumente") or path.startswith("/api/v1/lv") or path.startswith("/api/v1/nachtraege"):
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
