# seed-bedenken-pruefschritte.ps1
# Legt fuer alle bestehenden Bedenkenanzeigen einen Pruefschritt 1
# ("Importiert aus Bestandsdaten", abgeschlossen=TRUE) an.
# Idempotent: ON CONFLICT (vorgang_id, schritt) DO NOTHING.

$ErrorActionPreference = 'Stop'

Write-Host "=== Seed Schritt 1 fuer Bedenkenanzeigen ===" -ForegroundColor Cyan

$sql = @'
SET search_path TO tenant_tlbv, shared, public;

WITH admin AS (
    SELECT id FROM shared.benutzer WHERE email = 'admin@baupilot.de' LIMIT 1
)
INSERT INTO bedenkenpruefung (vorgang_id, schritt, titel, ergebnis, abgeschlossen, abgeschlossen_am, bearbeiter_id, erstellt_von)
SELECT v.id, 1, 'Erfassung', 'Importiert aus Bestandsdaten (Initial-Load 2026-04 bis 2026-05).', TRUE, v.erstellt_am, admin.id, admin.id
FROM vorgaenge v, admin
WHERE v.typ = 'bedenkenanzeige' AND NOT v.geloescht
ON CONFLICT (vorgang_id, schritt) DO NOTHING;

SELECT 'Bedenkenanzeigen gesamt' AS metrik, COUNT(*)::text AS wert FROM vorgaenge WHERE typ='bedenkenanzeige' AND NOT geloescht
UNION ALL
SELECT 'Pruefschritte Schritt 1 angelegt', COUNT(*)::text FROM bedenkenpruefung WHERE schritt=1
UNION ALL
SELECT 'Davon abgeschlossen', COUNT(*)::text FROM bedenkenpruefung WHERE schritt=1 AND abgeschlossen;
'@

$sql | docker exec -i baupilot-postgres psql -U baupilot -d baupilot -v ON_ERROR_STOP=1

if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Seed fehlgeschlagen." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Seed abgeschlossen ===" -ForegroundColor Green
