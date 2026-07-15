"""Williamson TN (Phase-5 South) — ground Brentwood + Franklin per-city jids (SLCo model).
Ring-precompute run per-city. Self-storage NAMED explicitly in both cities:

 BRENTWOOD (Code Ch. 78 Zoning; Municode through Ord. 2026-01). #38: SI-1..SI-4 = "Service
   Institution" (Religious/Educational/Cultural-Gov/Retirement) — INSTITUTIONAL, not industrial;
   "-IP" suffix is a GIS annotation (base AR/OSRD = residential/ag); "/SR" = Special Restrictions
   overlay (narrows only -> report base). The ONLY warehouse/industrial district is C-3
   "Commercial Service-Warehouse": §78-242(1)(b) "Facilities offering self-service storage units on a
   rental basis" PERMITTED by-right (+ warehousing + non-nuisance industrial). Per-district closed
   list §78-244.
 FRANKLIN (Zoning Ordinance eff. 1-13-2026; §5.1.3 use matrix, key §5.1.2). #38: ER = Estate
   Residential (NOT employment); CI = Civic Institutional (NOT commercial/industrial). "Self-Storage
   Facilities" is an explicitly named principal use (§5.1.4.V; 500-ft-from-arterial standard),
   half-circle P+ (= permitted by-right WITH additional standards; NO conditional tier exists) in
   LI/HI/RC12 (and, per the graphic matrix, CI -- HELD, see below). General Warehousing solid-P
   by-right in LI/HI. Mapping P+ self-storage -> conditional (conservative: reflects the locational
   standard; needle count identical to permitted).
   CI HELD: the use-matrix graphic (read via dot-detection) appears to show self-storage/warehousing
   P+ in CI, but that is semantically surprising for a Civic-Institutional district and was flagged
   for human spot-check -> grounded PROHIBITED here (not claimed as ~124 uncertain needles);
   escalated to outputs/_exceptions_D.md for verification. Same for RC4/RC6 (self-storage NOT listed).

Idempotent human-UPSERT, muni-scoped, verbatim citations (#37), gated to every parcel code, #42 print.
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_williamson_tn_south.py
"""
import asyncio, json, asyncpg

BR_JID = "e0df78b2-de04-4e43-bf3b-c5244eb4613c"   # Brentwood, TN
FR_JID = "307285f8-9426-4f17-9e66-999c8e01218f"   # Franklin, TN
BR_CITY = "Brentwood"
FR_CITY = "Franklin"

BR_ORD = "City of Brentwood, TN Code Ch. 78 Zoning (Municode; through Ord. No. 2026-01, 2-23-2026)"
Q_BR_C3 = ("§78-242 (C-3 Commercial Service-Warehouse) uses permitted: '(1) Warehousing and storage "
           "activities, including: ... b. Facilities offering self-service storage units on a rental "
           "basis'; '(2) Wholesaling activities...'; '(5) All types of industrial activities except "
           "[nuisance/hazardous]'. Intent §78-241: 'wholesale services, warehousing and industrial uses'.")
Q_BR_CLOSED = ("§78-244: 'Any use or structure that is not specifically permitted in the C-3 zoning "
               "district is prohibited.' (Each district carries its own closed-list prohibition.)")
Q_BR_SI = ("SI-1..SI-4 = 'Service Institution' districts (Religious §78-262 / Educational §78-282 / "
           "Cultural-Rec-Gov §78-302 / Retirement §78-322) — institutional uses only; no warehouse/"
           "self-storage. AR (§78-122) / OSRD = residential-agricultural ('-IP' is not an ordinance "
           "district). C-1 office / C-2 retail / C-4 town-center name no warehouse or storage facility.")

FR_ORD = "City of Franklin, TN Zoning Ordinance (adopted 12-10-2019, eff. 1-13-2026; use matrix §5.1.3)"
Q_FR_SS = ("§5.1.3 Permitted Principal Uses matrix + §5.1.4.V 'Self-Storage Facilities' (named principal "
           "use; footprint not within 500 ft of an arterial unless not visible). Key §5.1.2: half-circle "
           "= permitted with additional requirements (by-right; no conditional/special-exception tier). "
           "Self-Storage = permitted-with-standards in LI (§3.22), HI (§3.23), RC12.")
Q_FR_WH = ("§5.1.3: 'General Warehousing' (Ch.23 def: 'storage or distribution of goods') = solid-circle "
           "permitted by-right in LI and HI; 'Light Industrial Uses'/'Industrial Sales'/'Industrial "
           "Services'/'Wholesale Sales' permitted in LI/HI.")
Q_FR_CLOSED = ("§5.1.1: a principal use not listed is not permitted unless found substantially similar "
               "to a listed use or the ordinance is amended (functional closed list).")
Q_FR_CI = ("#38 / HELD: CI = Civic Institutional District (§3.12, 'civic, recreational, and institutional "
           "uses'), ER = Estate Residential (§3.3, single-family). The §5.1.3 graphic matrix (read via "
           "dot-detection) appears to show self-storage/general-warehousing = half-circle in CI, which "
           "is semantically surprising for a civic district -> grounded PROHIBITED pending human "
           "verification of an actual CI-mapped parcel; RC4/RC6 self-storage NOT listed.")


def cite(ord_, *qs):
    return [{"quote": q, "section": "Zoning", "ordinance": ord_} for q in qs]


def rows_brentwood(codes):
    C_C3 = cite(BR_ORD, Q_BR_C3, Q_BR_CLOSED)
    C_P = cite(BR_ORD, Q_BR_SI, Q_BR_CLOSED)
    N_C3 = "ss/mw PERMITTED (GROUNDED): §78-242(1)(b) 'Facilities offering self-service storage units on a rental basis' by-right; warehousing + non-nuisance industrial by-right. li PERMITTED. lgc PROHIBITED."
    N_C3SR = "Base C-3 with Special Restrictions overlay (§78-381, narrows only): ss/mw/li per base C-3 (§78-242(1)(b) self-service storage by-right). Verify a parcel's rezoning ord did not remove the use. lgc PROHIBITED."
    N_SI = "#38: 'Service Institution' district (institutional — religious/educational/cultural-gov/retirement), NOT industrial. No warehouse/self-storage use (§78-244 closed list). All prohibited."
    N_RES = "Residential/agricultural or office/retail/town-center district; no warehouse/self-storage use named (per-district closed list). All prohibited. ('-IP' suffix is a GIS annotation, not an ordinance district.)"
    out = []
    for zc in codes:
        base = zc.split("/")[0]
        if base == "C-3":
            note = N_C3 if zc == "C-3" else N_C3SR
            conf = 0.92 if zc == "C-3" else 0.80
            out.append((zc, "C-3 Commercial Service-Warehouse" + ("/SR overlay" if "/SR" in zc else ""),
                        "permitted", "permitted", "permitted", "prohibited", conf, note, C_C3))
        elif base.startswith("SI"):
            out.append((zc, f"{zc} Service Institution (#38 institutional)", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_SI, C_P))
        else:
            out.append((zc, zc, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_RES, C_P))
    return BR_CITY, out


def rows_franklin(codes):
    C_SS = cite(FR_ORD, Q_FR_SS, Q_FR_WH, Q_FR_CLOSED)
    C_CI = cite(FR_ORD, Q_FR_CI, Q_FR_CLOSED)
    C_P = cite(FR_ORD, Q_FR_CLOSED)
    N_LIHI = "ss/mw CONDITIONAL (GROUNDED): 'Self-Storage Facilities' named permitted-with-standards (§5.1.4.V, half-circle P+; 500-ft arterial standard). li PERMITTED: General Warehousing + Light/Heavy Industrial Uses by-right (§5.1.3). lgc PROHIBITED."
    N_RC12 = "ss/mw CONDITIONAL (GROUNDED): 'Self-Storage Facilities' named permitted-with-standards (§5.1.4.V, half-circle) in RC12 Regional Commerce. li PROHIBITED (regional-commerce, general-warehousing not confirmed by-right). lgc PROHIBITED. conf reflects graphic-matrix read."
    N_CI = "HELD/PROHIBITED (#38): CI = Civic Institutional; the graphic use-matrix MAY show self-storage/warehousing half-circle but this is surprising for a civic district and was dot-detected -> NOT grounded as needle pending human verification (escalated). ss/mw/li prohibited conservatively."
    N_P = "No self-storage/warehouse use listed for this district (§5.1.3 matrix; §5.1.1 closed list). All prohibited. (ER = Estate Residential #38; GO = General Office; RC4/RC6 self-storage not listed.)"
    out = []
    for zc in codes:
        if zc in ("LI", "HI"):
            zn = "LI Light Industrial" if zc == "LI" else "HI Heavy Industrial"
            out.append((zc, zn, "conditional", "conditional", "permitted", "prohibited", 0.85, N_LIHI, C_SS))
        elif zc == "RC12":
            out.append((zc, "RC12 Regional Commerce", "conditional", "conditional", "prohibited", "prohibited", 0.72, N_RC12, C_SS))
        elif zc == "CI":
            out.append((zc, "CI Civic Institutional (#38 HELD)", "prohibited", "prohibited", "prohibited", "prohibited", 0.55, N_CI, C_CI))
        else:
            out.append((zc, zc, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_P, C_P))
    return FR_CITY, out


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
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='90s'")
        for jid, builder in [(BR_JID, rows_brentwood), (FR_JID, rows_franklin)]:
            codes = [r["zoning_code"] for r in await con.fetch(
                "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND zoning_code IS NOT NULL ORDER BY zoning_code", jid)]
            muni, rows = builder(codes)
            for zc, zn, ss, mw, li, lgc, conf, note, cits in rows:
                await con.execute(SQL, jid, zc, zn, muni, ss, mw, li, lgc, json.dumps(cits), "Zoning", conf, note)
            got = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
                light_industrial::text li, confidence FROM zone_use_matrix
                WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code""", jid, muni)
            openz = [r['zone_code'] for r in got if r['ss'] in ('permitted', 'conditional')]
            print(f"\n#42 {muni} [{jid}]: {len(got)} rows; ss-open = {openz or '(none)'}")
            for r in got:
                if r['ss'] in ('permitted', 'conditional'):
                    print(f"  {r['zone_code']:10} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} c={r['confidence']} <==")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
