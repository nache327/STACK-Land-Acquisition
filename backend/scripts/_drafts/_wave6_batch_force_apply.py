"""Direct force-apply all 4 substrates with full output capture."""
import json, sys
from pathlib import Path
import httpx

API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"

def hardcap(s, cap=199):
    return s if not s or len(s) <= cap else s[:cap-1] + "…"

def apply(jid, prestage_file, label):
    path = Path("backend/data/wave6_pre_stage") / prestage_file
    rows = json.loads(path.read_text())
    # Dedupe + hardcap
    seen = set()
    clean = []
    for r in rows:
        k = (r["zone_code"], r.get("municipality"))
        if k in seen: continue
        seen.add(k)
        for c in r.get("citations", []):
            if c.get("quote"): c["quote"] = hardcap(c["quote"])
            if c.get("section"): c["section"] = hardcap(c["section"])
        clean.append(r)
    url = f"{API_BASE}/api/jurisdictions/{jid}/_upload-matrix-rows"
    print(f"\n=== {label} (rows={len(clean)}) ===")
    print(f"POST {url}")
    try:
        r = httpx.post(url, json={"rows": clean, "replace_existing": False}, timeout=180.0)
        print(f"HTTP {r.status_code}")
        try:
            body = r.json()
            if isinstance(body, dict):
                for k in ("inserted","updated","skipped","skipped_human","skipped_duplicate","errors"):
                    if k in body: print(f"  {k}: {body[k]}")
            else:
                print(str(body)[:400])
        except Exception:
            print(r.text[:400])
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {str(e)[:200]}")

apply("524b1948-f806-4007-b7e3-6ef7219c2b2c", "douglas_highlands_ranch.json",  "HIGHLANDS_RANCH")
apply("a44b7d24-de51-46fd-8148-0753e2570490", "arapahoe_englewood.json",       "ENGLEWOOD")
apply("c5e04fa4-08d7-464b-8b74-dd56fc1f3f17", "allegheny_fox_chapel.json",     "FOX_CHAPEL")
apply("c9af9445-0148-4660-ac80-930bcc8a2271", "mecklenburg_south_charlotte.json", "SOUTH_CHARLOTTE")
