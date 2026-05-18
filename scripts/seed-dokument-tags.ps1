# seed-dokument-tags.ps1
# Verknuepft die bestehenden 643 Dokumente mit den Default-Tag-Wurzeln aus
# Migration 008. Mapping basiert auf der bestehenden dokumente.kategorie-Spalte:
#   dokumentkategorie 'nachtrag'             -> Tag "Dokumenttyp/Nachtrag"
#   dokumentkategorie 'behinderungsanzeige'  -> Tag "Dokumenttyp/Behinderungsanzeige"
#   ... usw.
# Idempotent: ON CONFLICT (dokument_id, tag_id) DO NOTHING.

$ErrorActionPreference = 'Stop'

Write-Host "=== Seed Dokument-Tags ===" -ForegroundColor Cyan

$sql = @'
SET search_path TO tenant_tlbv, shared, public;

-- Mapping dokumentkategorie -> Tag-wert (im Default-Template Dokumenttyp).
-- Die Tags wurden in Migration 008 ueber das SYS-Projekt angelegt.
INSERT INTO dokument_tags (dokument_id, tag_id, erstellt_von)
SELECT d.id, t.id, 'migration_e11'
FROM dokumente d
JOIN tags t ON t.kategorie = 'Dokumenttyp' AND t.wert = (
    CASE d.kategorie::text
        WHEN 'lv' THEN 'LV'
        WHEN 'nachtrag' THEN 'Nachtrag'
        WHEN 'behinderungsanzeige' THEN 'Behinderungsanzeige'
        WHEN 'bedenkenanzeige' THEN 'Bedenkenanzeige'
        WHEN 'mangelanzeige' THEN 'Mangelanzeige'
        WHEN 'protokoll' THEN 'Protokoll'
        WHEN 'plan' THEN 'Plan'
        WHEN 'foto' THEN 'Foto'
        WHEN 'gutachten' THEN 'Gutachten'
        ELSE NULL
    END
)
WHERE d.kategorie::text IN ('lv','nachtrag','behinderungsanzeige','bedenkenanzeige','mangelanzeige','protokoll','plan','foto','gutachten')
  AND NOT d.geloescht
ON CONFLICT (dokument_id, tag_id) DO NOTHING;

-- Validierung
SELECT 'Dokumente gesamt' AS metrik, COUNT(*)::text AS wert FROM dokumente WHERE NOT geloescht
UNION ALL
SELECT 'Tag-Verknuepfungen', COUNT(*)::text FROM dokument_tags
UNION ALL
SELECT 'Dokumente mit Dokumenttyp-Tag',
       COUNT(DISTINCT dt.dokument_id)::text
       FROM dokument_tags dt JOIN tags t ON t.id = dt.tag_id
       WHERE t.kategorie = 'Dokumenttyp';
'@

$sql | docker exec -i baupilot-postgres psql -U baupilot -d baupilot -v ON_ERROR_STOP=1

if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Seed fehlgeschlagen." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Seed abgeschlossen ===" -ForegroundColor Green
