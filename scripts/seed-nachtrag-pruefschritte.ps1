# seed-nachtrag-pruefschritte.ps1
# Legt Pruefschritt 1 ("Erfassung") fuer alle bestehenden 322 NT-Vorgaenge an.
# F-101: Schritt 1 wird als "Importiert aus Bestandsdaten" markiert.
# Datum: 09.05.2026

$ErrorActionPreference = 'Stop'

Write-Host "=== Seed: Pruefschritte fuer bestehende Nachtraege ===" -ForegroundColor Cyan

$sql = @"
SET search_path TO tenant_tlbv, shared, public;

-- Admin-Benutzer-ID ermitteln
DO \$\$
DECLARE
    v_admin_id UUID;
    v_count INTEGER := 0;
    v_vorgang RECORD;
BEGIN
    SELECT id INTO v_admin_id FROM shared.benutzer WHERE email = 'admin@baupilot.de';
    IF v_admin_id IS NULL THEN
        RAISE EXCEPTION 'Admin-Benutzer nicht gefunden';
    END IF;

    FOR v_vorgang IN
        SELECT id, nummer FROM vorgaenge
        WHERE typ = 'nachtrag' AND NOT geloescht
        ORDER BY nummer
    LOOP
        INSERT INTO nachtragspruefung (
            vorgang_id, schritt, titel, ergebnis,
            bearbeiter_id, abgeschlossen, abgeschlossen_am,
            erstellt_von
        ) VALUES (
            v_vorgang.id, 1, 'Erfassung', 'Importiert aus Bestandsdaten',
            v_admin_id, TRUE, NOW(),
            v_admin_id
        )
        ON CONFLICT (vorgang_id, schritt) DO NOTHING;

        v_count := v_count + 1;
    END LOOP;

    RAISE NOTICE 'Pruefschritt 1 fuer % Nachtraege angelegt.', v_count;
END \$\$;

-- Validierung
SELECT COUNT(*) AS pruefschritte_gesamt FROM nachtragspruefung;
SELECT schritt, COUNT(*) AS anzahl FROM nachtragspruefung GROUP BY schritt ORDER BY schritt;
"@

$sql | docker exec -i baupilot-postgres psql -U baupilot -d baupilot -v ON_ERROR_STOP=1

if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Seed fehlgeschlagen." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Seed abgeschlossen ===" -ForegroundColor Green
Write-Host "Erwartetes Ergebnis: 322 Pruefschritte (Schritt 1) angelegt." -ForegroundColor Gray
