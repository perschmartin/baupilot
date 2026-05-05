# BP-V-18 — Entscheidungsprotokolle

**Vorlage gemaess Advocatus-Diaboli-Prozess (Konzeptpapier §11)**

---

## B-001 — Datenmodell: Bauteil-Ebene

**Datum:** 04. Mai 2026
**Entscheider:** Martin Persch
**AD-Vorbereitung:** 21. April 2026 (AD-Sitzung 001)
**Status:** ENTSCHIEDEN

**These:** Eigene Bauteil-Tabelle zwischen Projekt und LV/Vorgang einfuehren.

**AD-Kernargumente:**
Overengineering bei Eingebaeude-Projekten. Zuordnungs-Ambiguitaet bei gebaeudeuebergreifenden Nachtraegen. LV-Nummer als Surrogat. Tags statt Hierarchie.

**Entscheidung:** Bauteil-Ebene einfuehren mit drei Sicherungen:
1. Bauteil-Referenz optional (NULL erlaubt) an Vorgang und LV
2. Tag-System zusaetzlich fuer flexible Dimensionen
3. UI zeigt Bauteil-Ebene nur bei mehr als einem Bauteil an

**Begruendung:** 714 Nachtragsdateien beziehen sich konsistent auf Gebaeudeabschnitte. Ohne Bauteil-Ebene keine saubere Kausalanalyse. Optionaler FK und Tag-System fangen die Gegenargumente auf.

**Residualrisiken akzeptiert:**
- Migrationsschmerz bei Bauteil-Umbenennung (Mitigation: Audit-Log)
- Schwache Datenqualitaet in Altdaten (Mitigation: schrittweise Anreicherung)

---

## B-002 — Verknuepfungsanalyse: Zwei-Schichten-Modell

**Datum:** 04. Mai 2026
**Entscheider:** Martin Persch
**AD-Vorbereitung:** 21. April 2026 (AD-Sitzung 001)
**Status:** ENTSCHIEDEN

**These:** Deterministische Kaskade ueber Postgres-Fremdschluessel.

**AD-Kernargumente:**
Determinismus zu starr fuer unscharfe Beziehungen. Manuelle Verknuepfung skaliert nicht. Graph-Datenbanken waeren das natuerliche Werkzeug. LLM-Inferenz ist Bias-anfaellig.

**Entscheidung:** Zwei-Schichten-Modell:
- Schicht 1 (produktiv): Deterministische Kaskade mit vorgaenger_id, beziehungstyp, erstellt_von, konfidenz. Revisionssicher.
- Schicht 2 (Assistenz): LLM-Vorschlagssystem, das Kandidaten praesentiert. Mensch bestaetigt oder verwirft.

Keine Graph-Datenbank. Postgres-Rekursion reicht fuer Tiefen von 2 bis 5 Stufen.

**Begruendung:** Revisionssicherheit fuer Rechtsstreitigkeiten hat Vorrang. LLM-Vorschlaege beschleunigen die Verknuepfungsarbeit, ohne die Nachweisqualitaet zu gefaehrden.

**Residualrisiken akzeptiert:**
- Korrektur falscher Verknuepfungen nur ueber Audit-Log, nicht durch Loeschen
- LLM-Vorschlagsqualitaet abhaengig von Trainingsdaten und Prompts

---

## B-003 — Mandantenfaehigkeit: Schema-per-Tenant

**Datum:** 04. Mai 2026
**Entscheider:** Martin Persch
**AD-Vorbereitung:** 21. April 2026 (AD-Sitzung 001)
**Status:** ENTSCHIEDEN

**Varianten:**
A. Row-Level-Security (RLS)
B. Schema-per-Tenant
C. Datenbank-per-Tenant

**AD-Kernargumente:**
Gegen A: Policy-Fehler fuehrt zu Cross-Tenant-Leak. Gegen B: Connection-Pool-Bugs bei search_path. Gegen C: Hoher Betriebsaufwand, asymmetrische Migrationen.

**Entscheidung:** Variante B — Schema-per-Tenant.
Ein Postgres-Cluster, ein Schema pro Mandant. SET LOCAL search_path in Transaktionen.

**Begruendung:** Staerkere Trennung als RLS, weniger Overhead als DB-per-Tenant. Bei 5 bis 20 Mandanten unproblematisch. VS-NfD-Erweiterung spaeter moeglich, ohne Mandantenmodell zu aendern.

**Residualrisiken akzeptiert:**
- Connection-Pool-Bugs (Mitigation: SET LOCAL in Transaktionen, Integrationstests)
- Komplexere mandantenuebergreifende Reports (Mitigation: separates Reporting-Schema)
- Schema-Updates pro Mandant (Mitigation: Alembic-Schleife, Staging-Test)

---

## B-004 — Stack-Bestaetigung

**Datum:** 04. Mai 2026
**Entscheider:** Martin Persch
**Status:** ENTSCHIEDEN

**Stack:**
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2
- Datenbank: PostgreSQL 16, Qdrant 1.12+, MinIO
- LLM: LiteLLM → Ollama (Qwen 2.5, Llama 3.x), Embedding nomic-embed-text
- PDF: Docling (SPARK), Fallback pdfplumber, OCR PaddleOCR
- Frontend: React 18 + Vite, Tailwind (Pre-Build)
- Infrastruktur: Docker Compose

**Entscheidung:** Stack bestaetigt, keine Aenderungen.

**Begruendung:** SPARK-kompatibel, Python-zentriert, vollstaendig lokal betreibbar, portabel von gmktec zu TLBV-Workstation.

---

**Dokumentstatus:** Vier Entscheidungen protokolliert, 04. Mai 2026.
