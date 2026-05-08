# BauPilot - FLI Firmen-Seed
# Legt die Projektbeteiligten des FLI-Projekts an.
# Idempotent: Vorhandene Firmen werden uebersprungen.

$ErrorActionPreference = "Stop"

$Container = "baupilot-postgres"
$DB        = "baupilot"
$User      = "baupilot"

Write-Host "BauPilot - FLI Firmen-Seed" -ForegroundColor Cyan

$sql = @"
SET search_path TO tenant_tlbv, shared, public;
BEGIN;

-- Firmen fuer FLI-Projekt
INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'TLBV Thueringen', 'TLBV', 'Bauherr', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'TLBV' AND f.projekt_id = p.id);

INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'BWP Architekten', 'BWP', 'Generalplaner', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'BWP' AND f.projekt_id = p.id);

INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'AGE Generalunternehmer', 'AGE', 'Generalunternehmer (extern)', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'AGE' AND f.projekt_id = p.id);

INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'HTI Hochbau', 'HTI', 'Generalunternehmer (intern, Hochbau)', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'HTI' AND f.projekt_id = p.id);

INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'ROM TGA', 'ROM', 'Generalunternehmer (intern, TGA)', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'ROM' AND f.projekt_id = p.id);

INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'IBB Ingenieurbuero', 'IBB', 'Fachbuero TGA (Sub GP)', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'IBB' AND f.projekt_id = p.id);

INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'VA Heinekamp', 'VAH', 'Fachbuero TWP (Sub GP)', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'VAH' AND f.projekt_id = p.id);

INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'Gerwert und Partner', 'GUP', 'Fachbuero (Sub GP)', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'GUP' AND f.projekt_id = p.id);

INSERT INTO firmen (projekt_id, name, kuerzel, rolle, erstellt_von)
SELECT p.id, 'Friedrich-Loeffler-Institut', 'FLI', 'Nutzer', 'seed'
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM firmen f WHERE f.kuerzel = 'FLI' AND f.projekt_id = p.id);

COMMIT;
"@

$sql | docker exec -i $Container psql -U $User -d $DB -q 2>&1 | ForEach-Object {
    if ($_ -match 'ERROR') { Write-Host "  FEHLER: $_" -ForegroundColor Red }
}

Write-Host "Validierung:" -ForegroundColor Cyan
echo "SET search_path TO tenant_tlbv; SELECT kuerzel, name, rolle FROM firmen WHERE NOT geloescht ORDER BY name;" | docker exec -i $Container psql -U $User -d $DB -t

Write-Host "Seed abgeschlossen." -ForegroundColor Green
