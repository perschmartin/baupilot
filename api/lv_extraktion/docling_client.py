"""
Client fuer den spark-docling Extraction Service.

Sendet PDFs an den spark-docling Container und gibt strukturierte
Ergebnisse zurueck. Konfiguration ueber Umgebungsvariablen.
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("baupilot.docling_client")

DOCLING_URL = os.getenv("DOCLING_URL", "http://spark-docling:8000")
DOCLING_TIMEOUT = int(os.getenv("DOCLING_TIMEOUT", "600"))  # 10 Minuten pro PDF


class DoclingClient:
    """HTTP-Client fuer spark-docling Service."""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or DOCLING_URL
        logger.info(f"DoclingClient initialisiert: {self.base_url}")

    def health(self) -> dict:
        """Statuscheck des spark-docling Service."""
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"spark-docling health check fehlgeschlagen: {e}")
            return {"status": "error", "detail": str(e)}

    def extract(self, pdf_bytes: bytes, filename: str = "document.pdf",
                extractor: str = "auto") -> dict[str, Any]:
        """
        PDF an spark-docling senden und Ergebnis zurueckholen.

        Args:
            pdf_bytes: PDF-Inhalt als Bytes
            filename: Dateiname (fuer Logging)
            extractor: "auto", "docling", oder "pdfplumber"

        Returns:
            {
                "filename": str,
                "extractor": str,
                "pages": int,
                "markdown": str,
                "tables": [{"page": int, "header": [...], "rows": [[...], ...]}, ...]
            }
        """
        try:
            r = httpx.post(
                f"{self.base_url}/extract",
                files={"datei": (filename, pdf_bytes, "application/pdf")},
                params={"extractor": extractor},
                timeout=DOCLING_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout bei Extraktion von {filename} ({DOCLING_TIMEOUT}s)")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"spark-docling Fehler bei {filename}: {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Extraktion fehlgeschlagen fuer {filename}: {e}")
            raise

    def extract_tables(self, pdf_bytes: bytes, filename: str = "document.pdf",
                       extractor: str = "auto") -> list[dict[str, Any]]:
        """Nur Tabellen aus PDF extrahieren."""
        try:
            r = httpx.post(
                f"{self.base_url}/extract/tables",
                files={"datei": (filename, pdf_bytes, "application/pdf")},
                params={"extractor": extractor},
                timeout=DOCLING_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("tables", [])
        except Exception as e:
            logger.error(f"Tabellen-Extraktion fehlgeschlagen fuer {filename}: {e}")
            raise
