"""
MinIO-Objektspeicher-Service fuer BauPilot.
Verwaltet Upload, Download und Bucket-Verwaltung.
"""

import os
import logging
from io import BytesIO
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger("baupilot.storage")

# Konfiguration aus Umgebungsvariablen
# Liest sowohl MINIO_ROOT_USER/PASSWORD als auch MINIO_ACCESS_KEY/SECRET_KEY
MINIO_ENDPOINT = os.getenv("MINIO_HOST", os.getenv("MINIO_ENDPOINT", "baupilot-minio")) + ":" + os.getenv("MINIO_API_PORT", "9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", os.getenv("MINIO_ACCESS_KEY", "baupilot"))
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", os.getenv("MINIO_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION"))
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MAX_UPLOAD_BYTES = int(os.getenv("BAUPILOT_MAX_UPLOAD_MB", "100")) * 1024 * 1024


def get_minio_client() -> Minio:
    """Erstellt einen MinIO-Client."""
    logger.info(f"MinIO-Verbindung: {MINIO_ENDPOINT}, User: {MINIO_ACCESS_KEY}")
    return Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def bucket_name_for_mandant(mandant_slug: str) -> str:
    """Erzeugt den Bucket-Namen fuer einen Mandanten."""
    return f"baupilot-{mandant_slug}".lower().replace("_", "-")


def ensure_bucket(client: Minio, bucket: str) -> None:
    """Erstellt den Bucket, falls er nicht existiert."""
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info(f"MinIO-Bucket '{bucket}' erstellt")
    except S3Error as e:
        logger.error(f"MinIO-Bucket-Fehler: {e}")
        raise


def build_object_path(
    projekt_kurz: str,
    dokument_id: str,
    version_nummer: int,
    dateiname: str,
) -> str:
    """Baut den MinIO-Objektpfad: {projekt}/{dok_id}/{version}/{dateiname}"""
    safe_name = dateiname.replace("/", "_").replace("\\", "_")
    return f"{projekt_kurz}/{dokument_id}/{version_nummer}/{safe_name}"


def upload_file(
    client: Minio,
    bucket: str,
    object_path: str,
    data: bytes,
    content_type: str,
) -> str:
    """Laedt eine Datei in MinIO hoch. Gibt den Objektpfad zurueck."""
    ensure_bucket(client, bucket)
    stream = BytesIO(data)
    client.put_object(
        bucket_name=bucket,
        object_name=object_path,
        data=stream,
        length=len(data),
        content_type=content_type,
    )
    logger.info(f"Upload: {bucket}/{object_path} ({len(data)} Bytes)")
    return object_path


def download_file(client: Minio, bucket: str, object_path: str) -> bytes:
    """Laedt eine Datei aus MinIO herunter."""
    try:
        response = client.get_object(bucket, object_path)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except S3Error as e:
        logger.error(f"Download-Fehler: {bucket}/{object_path}: {e}")
        raise


def file_exists(client: Minio, bucket: str, object_path: str) -> bool:
    """Prueft, ob eine Datei in MinIO existiert."""
    try:
        client.stat_object(bucket, object_path)
        return True
    except S3Error:
        return False


# MIME-Type Allowlist
ERLAUBTE_MIME_TYPEN = {
    "application/pdf",
    "image/jpeg", "image/png", "image/tiff", "image/gif", "image/bmp", "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint",
    "text/plain", "text/csv", "text/xml",
    "application/xml", "application/json",
    "application/zip", "application/x-7z-compressed", "application/x-rar-compressed",
    "application/octet-stream",
}

BLOCKIERTE_ENDUNGEN = {
    ".exe", ".bat", ".cmd", ".ps1", ".sh", ".msi", ".dll",
    ".com", ".scr", ".vbs", ".js", ".wsf", ".wsh",
}


def ist_erlaubter_mime_typ(mime_typ: str, dateiname: str) -> bool:
    """Prueft, ob der MIME-Typ erlaubt und die Endung nicht blockiert ist."""
    name_lower = dateiname.lower()
    for endung in BLOCKIERTE_ENDUNGEN:
        if name_lower.endswith(endung):
            return False
    return mime_typ in ERLAUBTE_MIME_TYPEN


def ist_erlaubte_groesse(groesse_bytes: int) -> bool:
    """Prueft, ob die Dateigroesse im erlaubten Bereich liegt."""
    return 0 < groesse_bytes <= MAX_UPLOAD_BYTES
