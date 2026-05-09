-- Fix: LV 101/102 Positionen bereinigen (Limit-3-Testlauf)
-- Datum: 08.05.2026
-- Problem: Erster Testlauf (--limit 3) hat 33+60=93 Positionen eingefuegt.
--          Volllauf hat dann "existiert bereits mit 25/48 Positionen" gemeldet
--          und uebersprungen. Die Differenz (33→25, 60→48) deutet auf 
--          Duplikat-Bereinigung durch ON CONFLICT hin, aber die Daten sind
--          moeglicherweise unvollstaendig.
-- 
-- Loesung: Positionen loeschen, dann Volllauf wiederholen (nur diese 2 + 23 Fehler-LVs)

SET search_path TO tenant_tlbv, shared, public;

-- Vorher zaehlen
SELECT l.nummer, l.bezeichnung, COUNT(p.id) AS positionen
FROM leistungsverzeichnisse l
JOIN lv_positionen p ON p.lv_id = l.id
WHERE l.nummer IN (101, 102)
GROUP BY l.nummer, l.bezeichnung;

-- Positionen loeschen (LV-Metadaten bleiben)
DELETE FROM lv_positionen
WHERE lv_id IN (
    SELECT id FROM leistungsverzeichnisse WHERE nummer IN (101, 102)
);

-- Nachher zaehlen (soll 0 sein)
SELECT l.nummer, COUNT(p.id) AS positionen
FROM leistungsverzeichnisse l
LEFT JOIN lv_positionen p ON p.lv_id = l.id
WHERE l.nummer IN (101, 102)
GROUP BY l.nummer;
