-- Fix: LV-Positionen Spaltenlaengen (Volllauf-Fehler)
-- Datum: 08.05.2026
-- Problem: einheit VARCHAR(31) zu kurz, kurztext VARCHAR(1000) zu kurz
-- Betroffen: 13 LVs (106,110,115,116,120,121,127,130,205,230,402,403)
-- Keine neue Migration — Hotfix auf Alembic 006

SET search_path TO tenant_tlbv, shared, public;

-- einheit: "Montagewände mit Brandschutzanforderung F30" etc.
ALTER TABLE lv_positionen ALTER COLUMN einheit TYPE VARCHAR(100);

-- kurztext: 400er-LVs haben Langtext im Kurztext (>1000 Zeichen)
ALTER TABLE lv_positionen ALTER COLUMN kurztext TYPE TEXT;

-- Validierung
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'tenant_tlbv'
  AND table_name = 'lv_positionen'
  AND column_name IN ('einheit', 'kurztext')
ORDER BY column_name;
-- Erwartet: einheit VARCHAR(100), kurztext TEXT (kein Limit)
