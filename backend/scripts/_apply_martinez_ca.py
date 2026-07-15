"""Martinez CA (Contra Costa) — ground per-city (batch-2).

Martinez Municipal Code Title 22 Zoning (eCode360 MA6944, code-date 2026-04-20). Self-storage/mini-storage
is NAMED as a use in EXACTLY ONE district — CC Central Commercial, CONDITIONAL (§22.16.080.K.10 "Storage
buildings for household goods (including mini-storage and self-storage facilities)"). Named-confinement
(Boonton rule) governs:
  - H-I Heavy / L-I Light Industrial (§22.18): "Warehouses and storage" is CONDITIONAL (CUP, §22.18.060.K),
    NOT by-right; by-right = light/heavy industry, packing/shipping, wholesale. Self-storage NOT named.
    -> conditional-warehouse does NOT trigger the ss/mw convention + self-storage confined to CC ->
    ss/mw PROHIBITED, li PERMITTED. (H-I 81 + L-I 22 in-ring = li-armed NO-OP, NOT self-storage needles.)
  - SC Service Commercial: warehouse by-right (§22.16.070.EE) but self-storage confined to CC -> ss/mw
    prohibited, li permitted.
  - CC Central Commercial: self-storage CONDITIONAL (named). M-combining districts including CC
    ("M-...  /CC", per §22.08.010 M district permits all combined districts' uses) inherit -> ss/mw conditional.
  - #38: county-style M-12/M-17/M-29 on Martinez parcels = Multiple-Family Residential -> prohibited.
    ECD-* = Environmental Conservation overlay -> prohibited. W-3 = Controlled Heavy Industrial -> li only.

Idempotent human-UPSERT, muni-scoped, verbatim cites (#37), gated to every parcel code, #42 print.
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_martinez_ca.py
"""
import asyncio, json, asyncpg

JID = "7ad622d4-0d36-4fe5-ad8b-53352bdac162"
CITY = "Martinez"
ORD = "City of Martinez, CA Municipal Code Title 22 Zoning (eCode360 MA6944, 2026)"


def cite(*qs):
    return [{"quote": q, "section": "Title 22", "ordinance": ORD} for q in qs]


Q_CC = ("§22.16.080.K.10 (CC Central Commercial, conditional uses): 'Storage buildings for household goods "
        "(including mini-storage and self-storage facilities)' — the ONLY naming of self-storage in Title 22.")
Q_IND = ("H-I/L-I (§22.18): by-right = light/heavy industry, packing/shipping (§22.18.030/.040 N), wholesale "
         "(R); 'Warehouses and storage' = CONDITIONAL only (§22.18.060.K). Self-storage NOT named in H-I/L-I/SC.")
Q_CL = ("Self-storage named + confined to CC (§22.16.080.K.10); conditional-warehouse in H-I/L-I does not "
        "bump self-storage (named-confinement). SC warehouse by-right (§22.16.070.EE) but self-storage not named there.")

CITS_CC = cite(Q_CC, Q_CL)
CITS_IND = cite(Q_IND, Q_CL)


def classify(zc):
    u = zc.upper()
    # CC self-storage (named conditional) + M-combining that includes CC
    if zc == "CC" or ("/CC" in u) or u.endswith("CC") and u.startswith("M-"):
        return ("conditional", "conditional", "prohibited", "prohibited", 0.85 if zc == "CC" else 0.75,
                "ss/mw CONDITIONAL (GROUNDED): self-storage named conditional in CC (§22.16.080.K.10)" +
                ("" if zc == "CC" else "; M-combining district inherits CC uses (§22.08.010).") + " li prohibited (commercial).",
                CITS_CC)
    # industrial (li permitted, ss/mw prohibited): H-I, L-I, W-3, SC, and M-combining incl. L-I/C-I/R&D/SC
    if zc in ("H-I", "L-I", "W-3", "SC") or any(t in u for t in ("/L-I", "/C-I", "R&D/L-I", "M-SC/", "M-PA/C-I", "M-R&D/L")):
        return ("prohibited", "prohibited", "permitted", "prohibited", 0.82,
                "ss/mw PROHIBITED: warehouse CUP-only (H-I/L-I §22.18.060.K) or by-right in SC but self-storage confined to CC. li PERMITTED (industry/warehouse). lgc PROHIBITED.",
                CITS_IND)
    if u.startswith("ECD"):
        return ("prohibited", "prohibited", "prohibited", "prohibited", 0.65,
                "PROHIBITED: ECD Environmental Conservation overlay (§22.24) — conservation/open-space; no self-storage.", CITS_CC)
    conf = 0.65 if (zc.startswith(("P-1", "AV/", "HPUD", "M-")) or zc in ("U", "DS", "FRANKLIN CANYON AREA", "TC")) else 0.85
    return ("prohibited", "prohibited", "prohibited", "prohibited", conf,
            "PROHIBITED: residential/agri/office/civic/rec/mixed-non-CC; self-storage confined to CC (§22.16.080.K.10). M-12/17/29 = Multiple-Family Residential.", CITS_CC)


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
    con = await asyncpg.connect(url, timeout=90, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        codes = [r["zoning_code"] for r in await con.fetch(
            "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND city=$2 AND zoning_code IS NOT NULL ORDER BY zoning_code", JID, CITY)]
        openz = []
        for zc in codes:
            ss, mw, li, lgc, conf, note, cites = classify(zc)
            await con.execute(SQL, JID, zc, zc, CITY, ss, mw, li, lgc, json.dumps(cites), "Title 22", conf, note)
            if ss in ("permitted", "conditional"):
                openz.append(f"{zc}({ss[:4]})")
        print(f"#42 {CITY}: {len(codes)} rows; ss-open = {openz}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
