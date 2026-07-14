"""Acton MA — Stage-4 FULL close (2026-07-13). Zero held cells. 26 base districts.

TAIL (Rt-2 tech/office corridor, wealthy). STRONG NEEDLE MUNI: "Warehouse" is a defined use that
EXPLICITLY INCLUDES self-storage, and it is permitted BY-RIGHT in 8 industrial/office-park districts
-> self-storage permitted by-right there.

Grounding — Town of Acton Zoning Bylaw (2026 ed., amended through May 2025; acton-ma.gov View/659),
§3 Table of Principal Uses + §3.6 definitions:
  Legend: Y=permitted by right; N=prohibited; SPA/SPP/SPS=special permit (BoA/Planning/Select).
    Closed by construction (every use has an explicit value per district; §3 "USE ... permitted ...
    except where other regulations apply").
  ss/mw PERMITTED (by-right) in OP-1, OP-2, PM, GI, LI, LI-1, SM, TD: §3.6.1 "Warehouse" is DEFINED
    as "A building used primarily for the enclosed storage of goods, and not a Distribution Center...;
    a personal self-storage facility or mini-warehouse" — i.e. self-storage IS a Warehouse — and
    §3.6.1 Warehouse = Y (by-right) in those 8 districts (N in KC/LB/WAV and all residential/village).
  li PERMITTED in OP-1, OP-2, PM, GI, LI, LI-1, SM, TD (§3.6.3 Manufacturing = Y); CONDITIONAL in
    WAV, KC (Manufacturing = SPS); prohibited elsewhere.
  lgc PROHIBITED everywhere: no named garage-condo / vehicle-storage principal use ("Warehouse" is
    enclosed goods/personal self-storage, not a luxury vehicle garage-condo); closed table.

Rebind: MAPC layer 2 (strip ^2) normalizes inconsistent assessor variants (OP1/OP-1, R2/R-2,
EAV2/EAV-2, R108/R-10, R84/R-8/4) to the 26 bylaw district codes.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via pdfplumber table extraction.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_acton.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "ACTON"
CITED_SUBSECTION = "§3.6.1 Warehouse (def + Table) / §3.6.3 Manufacturing + §3 Table of Principal Uses"
ORD = ("Town of Acton Zoning Bylaw (2026 ed., amended through May 2025; acton-ma.gov View/659), "
       "§3 Table of Principal Uses + §3.6 definitions")

Q_SS = ("§3.6.1 defines 'Warehouse – A building used primarily for the enclosed storage of goods, and "
        "not a Distribution Center as defined in Section 3.6.2; a personal self-storage facility or "
        "mini-warehouse.' Table §3.6.1 'Warehouse' = Y (by-right) in OP-1, OP-2, PM, GI, LI, LI-1, SM, "
        "TD; N in KC, LB, WAV, all residential/village/conservation. So self-storage is permitted "
        "by-right where Warehouse is.")
Q_LI = ("Table §3.6.3 'Manufacturing' = Y (by-right) in OP-1, OP-2, PM, GI, LI, LI-1, SM, TD; SPS in "
        "WAV and KC; N elsewhere. §3.6.2 'Distribution Center' = SPS in OP-2/PM/TD only.")
Q_LGC = ("No named luxury garage-condo / vehicle-storage principal use ('Warehouse' §3.6.1 is enclosed "
         "goods storage / personal self-storage, not a vehicle garage-condo). Closed table -> lgc "
         "prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "§3.6", "ordinance": ORD} for q in qs]


N_IND = ("ss/mw PERMITTED (GROUNDED): §3.6.1 'Warehouse' (defined to INCLUDE 'a personal self-storage "
         "facility or mini-warehouse') = Y (by-right) here. li PERMITTED (GROUNDED): §3.6.3 "
         "Manufacturing = Y (by-right). lgc PROHIBITED: no named vehicle garage-condo use.")
N_COND = ("li CONDITIONAL: §3.6.3 Manufacturing = SPS (special permit) here. ss/mw PROHIBITED: §3.6.1 "
          "Warehouse = N here. lgc PROHIBITED.")
N_PROHIB = ("All prohibited. §3.6.1 Warehouse + §3.6.3 Manufacturing = N in this "
            "residential/village/conservation/limited-business district; no named garage-condo use.")

NEEDLE = ["OP-1", "OP-2", "PM", "GI", "LI", "LI-1", "SM", "TD"]
COND = ["WAV", "KC"]
ZN = {"OP-1": "Office Park 1", "OP-2": "Office Park 2", "PM": "Powder Mill District",
      "GI": "General Industrial", "LI": "Light Industrial", "LI-1": "Light Industrial 1",
      "SM": "Small Manufacturing", "TD": "Technology District", "WAV": "West Acton Village",
      "KC": "Kelley's Corner", "LB": "Limited Business", "ARC": "Agric. Rec. Conservation",
      "EAV": "East Acton Village", "EAV-2": "East Acton Village 2", "NAV": "North Acton Village",
      "SAV": "South Acton Village", "PCRC": "Planned Cons. Residential Community",
      "R-10": "Residence 10", "R-10/8": "Residence 10/8", "R-2": "Residence 2", "R-4": "Residence 4",
      "R-8": "Residence 8", "R-8/4": "Residence 8/4", "R-A": "Residence A", "R-AA": "Residence AA",
      "VR": "Village Residential"}

VERDICTS = []
for zc, zn in ZN.items():
    if zc in NEEDLE:
        ss = mw = "permitted"; li = "permitted"; note = N_IND; conf = 0.90
    elif zc in COND:
        ss = mw = "prohibited"; li = "conditional"; note = N_COND; conf = 0.82
    else:
        ss = mw = "prohibited"; li = "prohibited"; note = N_PROHIB; conf = 0.92
    VERDICTS.append({"zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
                     "light_industrial": li, "luxury_garage_condo": "prohibited",
                     "citations": cite(Q_SS, Q_LI, Q_LGC), "cited_subsection": CITED_SUBSECTION,
                     "confidence": conf, "notes": note})

SQL = """INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
 light_industrial, luxury_garage_condo, citations, cited_subsection, confidence, human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,$8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
 light_industrial=EXCLUDED.light_industrial, luxury_garage_condo=EXCLUDED.luxury_garage_condo,
 citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
 human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for v in VERDICTS:
            await con.execute(SQL, JID, v["zone_code"], v["zone_name"], MUNI,
                              v["self_storage"], v["mini_warehouse"], v["light_industrial"],
                              v["luxury_garage_condo"], json.dumps(v["citations"]),
                              v["cited_subsection"], v["confidence"], v["notes"])
        rows = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
            light_industrial::text li, luxury_garage_condo::text lgc, confidence, human_reviewed hr
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
            ORDER BY zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI} rows post-apply ({len(rows)}):")
        for r in rows:
            print(f"  {r['zone_code']:7} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
