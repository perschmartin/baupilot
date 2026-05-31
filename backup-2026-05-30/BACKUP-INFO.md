# Rollback-Sicherung 30. Mai 2026

**Erstellt durch:** Claude (Nachtsitzung, Martin schlaeft)
**Zeitpunkt:** 30.05.2026, ca. 23:00 Uhr
**Grund:** Vor Dokumentations-Updates und Vorbereitung neuer Dateien

## Was gesichert wurde

- `CLAUDE.md` — Originalversion vom 18.05.2026
- `BauPilot-Roadmap-2026-05-18.md` — Roadmap-Original

## Was NICHT veraendert wurde (Live-System unberuehrt)

- api/* — kein File angefasst
- frontend/index.html — kein File angefasst
- alembic/* — keine Migration angefasst
- docker-compose*.yaml — nicht angefasst
- .env — nicht angefasst
- scripts/* — keine bestehenden Skripte geaendert

## Rollback-Anweisung

Falls CLAUDE.md-Update Probleme macht:
```powershell
Copy-Item "C:\SPARK\spark-baupilot\backup-2026-05-30\CLAUDE.md" "C:\SPARK\spark-baupilot\CLAUDE.md" -Force
```

Die neuen Dokumentationsdateien (Konzept v0.5, Projektanweisung v0.5) sind NEUE Dateien
und ueberschreiben nichts — zum Rollback einfach loeschen.
