import httpx, json, sys

r = httpx.post("http://localhost:8070/extract",
    files={"datei": ("106_Rohbau.pdf", open(sys.argv[1], "rb"), "application/pdf")},
    timeout=300)
d = r.json()
print(f"Pages: {d['pages']}")
print(f"Tables: {len(d['tables'])}")
print(f"Extractor: {d['extractor']}")
print(f"Duration: {d['duration_seconds']}s")
print("---MARKDOWN (erste 3000 Zeichen)---")
print(d["markdown"][:3000])
print("---TABLES---")
for i, t in enumerate(d["tables"]):
    print(f"Table {i}: header={t['header']}, rows={len(t['rows'])}")
    for row in t["rows"][:3]:
        print(f"  {row}")
