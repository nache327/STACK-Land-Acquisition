"""Essex County NJ (jid 67541a18) — Session-B Stage-4 grounding: Livingston + Millburn + Roseland.

Shared county with A (A = Fairfield + West Caldwell). NJ name-bound → no rebind. municipality = exact
parcels.city (verified via SELECT DISTINCT): 'Livingston township', 'Millburn township',
'Roseland borough'. Muni-scoped human UPSERT (#33), verbatim citations (#37), verify-and-print (#42),
closed-list sweep (#57/#58), lgc-unnamed→prohibited.

=== LIVINGSTON (eCode360 LI1238, Ch. 170 Land Use; print guid=10295328) ===
NEEDLES:
  I  §170-117 Limited Industrial — A.(6) "Moving and storage operations and self-storage facilities"
     (by-right primary use) → ss/mw PERMITTED; limited industrial/manufacturing/assembly permitted → li PERMITTED.
  CI §170-118 Commercial Industrial — A.(3)(c) "Warehouses, including self-storage facilities
     (mini-warehouses)" (by-right permitted use) → ss/mw PERMITTED; (3) manufacturing/industry → li PERMITTED.
  R-L §170-115 / R-L2 §170-116 Research Laboratory — self-storage NOT in the district's closed primary-use
     list, BUT §170-88K "Self-storage facilities... shall be permitted only in the R-L and R-L2 Zones as
     conditional uses" → ss/mw CONDITIONAL. li PROHIBITED (office/research; R-L2 expressly bars manufacturing).
  #38: R-L is "Research Laboratory" (office/research/institutional), NOT residential despite the R- prefix —
     confirmed via §170-115A use list. It is a storage CONDITIONAL zone (via §170-88K), not a li zone.
  TENSION FLAGGED (see outputs/_exceptions_B.md): §170-88K says self-storage is permitted "only in R-L/R-L2
     as conditional uses" while I/CI expressly list it as a by-right primary use. Primary reading (grounded
     here): by-right in I/CI + conditional in R-L/R-L2 coexist (§170-88 is a permissive conditional-use
     section; a by-right listed use is not a "conditional use" in that zone). Weaker exclusivity reading
     (the "only" + §170-88 precedence clause) would demote I/CI to prohibited — coordinator/Nache call.
PROHIBITED: all residential (R-1..R-6, R-5A/B/C/E/F/I/J, R-G, AH Adult Housing), business (B Central,
  B-1 General, B-2 Highway, BN), professional office (P-B/P-B1/P-B2/P-B3), designed shopping (D-S/D-S2),
  hospital (H-H §170-118.2), water conservation (WRC §170-95). None list self-storage/warehouse.

=== MILLBURN (eCode360 MI4080, Ch. DRZ; Art.6 print guid=35143140) ===
NEEDLE:
  CMO §DRZ-606.9 Commercial/Medical Office — b.2 "Wholesale business, light assembly and manufacturing,
     scientific and other research facilities, WAREHOUSES, and offices..." warehouse BY-RIGHT + self-storage
     UNNAMED anywhere in Millburn + NO global self-storage clause → warehouse-by-right convention:
     ss/mw CONDITIONAL, li PERMITTED (light assembly/manufacturing). [[feedback_warehouse_conditional_convention]]
  #38: Millburn "C" = §DRZ-606.1 Conservation-Recreation (the ~650-ac South Mountain Reservation), NOT a
     commercial district → PROHIBITED, not a needle (coordinator's "C/CMO" — only CMO is the needle).
PROHIBITED: C (Conservation-Rec), CE (Conservation-Educ §DRZ-606.12), CD (Cultural §DRZ-606.10), OR-1/2/3
  (Office Research §DRZ-606.8 — offices/retail/hotel/residential, no warehouse), B-1/B-2/B-3/B-4 (Business),
  R-O (Residential-Office §DRZ-606.11), P (not a Ch. DRZ district — Public/Park data code, conservative),
  residential R-1-5/R-3/R-4/R-5/R-6/R-7/R-8.

=== ROSELAND (eCode360 RO4067, Ch. 30 Land Development; Art.IV print guid=34523834) ===
NEEDLE:
  RM = §30-404.5 Research/Manufacturing (R/M) Zone — a.2 "Limited manufacturing, assembly and light
     industrial operations" (permitted principal) → li PERMITTED; c.1 "Self-storage facility" listed as a
     Permitted Conditional Use → ss/mw CONDITIONAL. NJ catch (b): self-storage is a NAMED conditional use
     CONFINED to R/M (no other Roseland district lists it) → named beats convention.
  #38: Roseland "C"/"CR" = §30-30 Conservation / Conservation-Recreation, NOT commercial (coordinator's
     "C/CR/OB-3" — those are conservation/office; the real needle is RM). OB-1/2/3 = office/labs only.
PROHIBITED: C/CR (Conservation), OB-2/OB-3 (Office Building §30-404.4 — offices/research labs, no storage),
  B-1/B-2 (Business §30-404.3 — retail/office), residential R-1/R-2/R-3/R-4, R-13/AH-7.

Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_essex_nj_batchB.py
"""
import asyncio, json, asyncpg

JID = "67541a18-c599-423b-bf05-d68153af1e2f"  # Essex County, NJ


def cite(quotes, chapter, ordinance):
    return [{"quote": q, "section": chapter, "ordinance": ordinance} for q in quotes]


# ───────────────────────── LIVINGSTON ─────────────────────────
LIV = "Livingston township"
LIV_ORD = "Township of Livingston, NJ Code Ch. 170 Land Use (eCode360 LI1238)"
LIV_SUB = "§170-117 (I); §170-118 (CI); §170-115/116 (R-L/R-L2); §170-88K (self-storage conditional-use)"
Q_LIV_I = ("§170-117 I Limited Industrial District, A. Primary intended use: '(6) Moving and storage "
           "operations and self-storage facilities.' Also '(3) Limited industrial, manufacturing, "
           "assembly and packaging uses.'")
Q_LIV_CI = ("§170-118 CI Commercial Industrial District, A. Permitted uses: '(3) Manufacturing/industry. "
            "... (c) Warehouses, including self-storage facilities (mini-warehouses).'")
Q_LIV_RL = ("§170-88 Conditional uses, K. Self-storage facilities: '(1) Self-storage facilities ... shall "
            "be permitted only in the R-L and R-L2 Zones as conditional uses ...'. R-L primary uses "
            "(§170-115A) are office/research/institutional (closed list); self-storage enters via §170-88K.")
Q_LIV_PROH = ("Self-storage/warehouse are named only in I (§170-117A(6)), CI (§170-118A(3)(c)) by-right and "
              "R-L/R-L2 via §170-88K conditional. No other Livingston district lists them; residential/"
              "business/office/shopping/hospital/conservation districts → self-storage prohibited; no named "
              "luxury-garage-condo use anywhere → lgc prohibited.")

L_I = ("ss/mw PERMITTED by-right (§170-117A(6) 'self-storage facilities'). li PERMITTED (limited industrial/"
       "manufacturing/assembly). lgc prohibited.")
L_CI = ("ss/mw PERMITTED by-right (§170-118A(3)(c) 'Warehouses, including self-storage facilities "
        "(mini-warehouses)'). li PERMITTED (manufacturing/industry). lgc prohibited.")
L_RL = ("ss/mw CONDITIONAL via §170-88K ('permitted only in the R-L and R-L2 Zones as conditional uses'). "
        "li prohibited — office/research district (R-L2 expressly bars manufacturing). #38: R- prefix but "
        "NOT residential. Exclusivity-vs-coexistence tension flagged to coordinator.")
L_RES = "Residential district — no self-storage/warehouse/manufacturing use listed. All prohibited."
L_BUS = "Business district (retail/commercial) — self-storage/warehouse not listed; li prohibited."
L_OFF = "Professional office district — offices only; no storage/warehouse; li prohibited."
L_SHOP = "Designed shopping center — retail; no self-storage/warehouse; li prohibited."
L_CONS = "Water conservation district (§170-95) — conservation; all prohibited."
L_HOSP = "Hospital/health care district (§170-118.2) — institutional; no storage; li prohibited."

# code, name, ss, mw, li, lgc, conf, note
LIV_R = [
    ("I","I Limited Industrial","permitted","permitted","permitted","prohibited",0.90,L_I),
    ("CI","CI Commercial Industrial","permitted","permitted","permitted","prohibited",0.90,L_CI),
    ("R-L","R-L Research Laboratory","conditional","conditional","prohibited","prohibited",0.80,L_RL),
    ("R-L2","R-L2 Research Laboratory","conditional","conditional","prohibited","prohibited",0.80,L_RL),
    ("R-1","R-1 Single Family","prohibited","prohibited","prohibited","prohibited",0.92,L_RES),
    ("R-2","R-2 Single Family","prohibited","prohibited","prohibited","prohibited",0.92,L_RES),
    ("R-3","R-3 Single Family","prohibited","prohibited","prohibited","prohibited",0.92,L_RES),
    ("R-4","R-4 Single Family","prohibited","prohibited","prohibited","prohibited",0.92,L_RES),
    ("R-5","R-5 Residence","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-5A","R-5A Residence","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-5B","R-5B Residence","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-5C","R-5C Residence","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-5E","R-5E Residence","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-5F","R-5F Residence","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-5I","R-5I Residence","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-5J","R-5J Residence","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-6","R-6 Sr Citizens Housing","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("R-G","R-G Residence","prohibited","prohibited","prohibited","prohibited",0.75,L_RES),
    ("AH","AH Adult Housing","prohibited","prohibited","prohibited","prohibited",0.90,L_RES),
    ("B","B Central Business","prohibited","prohibited","prohibited","prohibited",0.86,L_BUS),
    ("B-1","B-1 General Business","prohibited","prohibited","prohibited","prohibited",0.86,L_BUS),
    ("B-2","B-2 Highway Business","prohibited","prohibited","prohibited","prohibited",0.86,L_BUS),
    ("BN","BN Business","prohibited","prohibited","prohibited","prohibited",0.70,L_BUS),
    ("P-B","P-B Professional Building","prohibited","prohibited","prohibited","prohibited",0.86,L_OFF),
    ("P-B1","P-B1 Professional Office","prohibited","prohibited","prohibited","prohibited",0.86,L_OFF),
    ("P-B2","P-B2 Professional Office","prohibited","prohibited","prohibited","prohibited",0.86,L_OFF),
    ("P-B3","P-B3 Professional Office","prohibited","prohibited","prohibited","prohibited",0.86,L_OFF),
    ("D-S","D-S Designed Shopping Center","prohibited","prohibited","prohibited","prohibited",0.86,L_SHOP),
    ("D-S2","D-S2 Designed Shopping Center","prohibited","prohibited","prohibited","prohibited",0.86,L_SHOP),
    ("WRC","WRC Water Conservation","prohibited","prohibited","prohibited","prohibited",0.88,L_CONS),
    ("H-H","HH Hospital Health Care","prohibited","prohibited","prohibited","prohibited",0.85,L_HOSP),
]
LIV_CITE = cite([Q_LIV_I, Q_LIV_CI, Q_LIV_RL, Q_LIV_PROH], "Ch. 170", LIV_ORD)

# ───────────────────────── MILLBURN ─────────────────────────
MIL = "Millburn township"
MIL_ORD = "Township of Millburn, NJ Ch. DRZ Development Regulations & Zoning (eCode360 MI4080)"
MIL_SUB = "§DRZ-606.9 (CMO); §DRZ-606.1 (C=Conservation-Rec); §DRZ-606.8 (OR)"
Q_MIL_CMO = ("§DRZ-606.9 Commercial/Medical Office CMO, b. Permitted Principal Uses: '2. Wholesale "
             "business, light assembly and manufacturing, scientific and other research facilities, "
             "warehouses, and offices operated in connection with the foregoing uses.'")
Q_MIL_PROH = ("Self-storage is not named in any Millburn district and there is no global self-storage "
              "clause; warehouses are by-right ONLY in CMO (§DRZ-606.9). All other districts "
              "(Conservation C/CE, Cultural CD, Office-Research OR, Business B-1..B-4, Residential-Office "
              "R-O, residential) do not permit warehouse/self-storage → prohibited; no garage-condo use → lgc prohibited.")
M_CMO = ("ss/mw CONDITIONAL via warehouse-by-right convention: §DRZ-606.9.b.2 lists 'warehouses' by-right "
         "and self-storage is unnamed with no global clause. li PERMITTED (light assembly and "
         "manufacturing). lgc prohibited.")
M_CONS = "Conservation/Conservation-Recreation district (§DRZ-606.1/606.12) — no commercial use; all prohibited."
M_CULT = "Cultural district (§DRZ-606.10) — no storage/warehouse; prohibited."
M_OR = ("Office Research district (§DRZ-606.8) — offices/retail/hotel/residential; no warehouse or "
        "self-storage; li prohibited.")
M_BUS = "Business district (Regional/Central Business §DRZ-606.5/606.7) — retail/office; no warehouse; prohibited."
M_RO = "Residential-Office district (§DRZ-606.11) — no storage/warehouse; prohibited."
M_RES = "Residential district — no storage/warehouse/manufacturing; all prohibited."
M_P = ("'P' is not a district in Ch. DRZ use tables (Public/Park data code); grounded prohibited "
       "conservatively — no storage use, 0 needle risk.")

MIL_R = [
    ("CMO","CMO Commercial/Medical Office","conditional","conditional","permitted","prohibited",0.82,M_CMO),
    ("C","C Conservation-Recreation","prohibited","prohibited","prohibited","prohibited",0.90,M_CONS),
    ("CE","CE Conservation-Educational/Cultural","prohibited","prohibited","prohibited","prohibited",0.88,M_CONS),
    ("CD","CD Cultural","prohibited","prohibited","prohibited","prohibited",0.85,M_CULT),
    ("OR-1","OR-1 Office Research","prohibited","prohibited","prohibited","prohibited",0.85,M_OR),
    ("OR-2","OR-2 Office Research","prohibited","prohibited","prohibited","prohibited",0.85,M_OR),
    ("OR-3","OR-3 Office Research","prohibited","prohibited","prohibited","prohibited",0.85,M_OR),
    ("B-1","B-1 Business","prohibited","prohibited","prohibited","prohibited",0.85,M_BUS),
    ("B-2","B-2 Business","prohibited","prohibited","prohibited","prohibited",0.85,M_BUS),
    ("B-3","B-3 Business","prohibited","prohibited","prohibited","prohibited",0.85,M_BUS),
    ("B-4","B-4 Business","prohibited","prohibited","prohibited","prohibited",0.85,M_BUS),
    ("R-O","R-O Residential-Office","prohibited","prohibited","prohibited","prohibited",0.85,M_RO),
    ("P","P Public/Park","prohibited","prohibited","prohibited","prohibited",0.65,M_P),
    ("R-1-5","R-1-5 Residence","prohibited","prohibited","prohibited","prohibited",0.90,M_RES),
    ("R-3","R-3 Residence","prohibited","prohibited","prohibited","prohibited",0.90,M_RES),
    ("R-4","R-4 Residence","prohibited","prohibited","prohibited","prohibited",0.90,M_RES),
    ("R-5","R-5 Residence","prohibited","prohibited","prohibited","prohibited",0.90,M_RES),
    ("R-6","R-6 Residence","prohibited","prohibited","prohibited","prohibited",0.90,M_RES),
    ("R-7","R-7 Residence","prohibited","prohibited","prohibited","prohibited",0.90,M_RES),
    ("R-8","R-8 Residence","prohibited","prohibited","prohibited","prohibited",0.90,M_RES),
]
MIL_CITE = cite([Q_MIL_CMO, Q_MIL_PROH], "Ch. DRZ", MIL_ORD)

# ───────────────────────── ROSELAND ─────────────────────────
ROS = "Roseland borough"
ROS_ORD = "Borough of Roseland, NJ Ch. 30 Land Development (eCode360 RO4067)"
ROS_SUB = "§30-404.5 (R/M); §30-404.4 (OB); §30-404.3 (B); §30-30 (C/CR Conservation)"
Q_ROS_RM = ("§30-404.5 Research/Manufacturing (R/M) Zone: a. Permitted Principal Uses '2. Limited "
            "manufacturing, assembly and light industrial operations'; c. Permitted Conditional Uses "
            "'1. Self-storage facility.'")
Q_ROS_PROH = ("Self-storage is named only in the R/M Zone (§30-404.5c.1) as a conditional use, and no "
              "other Roseland district lists self-storage or warehouse. OB Office Building (§30-404.4) = "
              "offices/research labs; B Business (§30-404.3) = retail/office; C/CR = Conservation (§30-30); "
              "residential → self-storage prohibited; no garage-condo use → lgc prohibited.")
R_RM = ("ss/mw CONDITIONAL — §30-404.5c.1 'Self-storage facility' listed as a Permitted Conditional Use; "
        "named & confined to R/M (named beats convention). li PERMITTED — a.2 'Limited manufacturing, "
        "assembly and light industrial operations' (permitted principal). lgc prohibited.")
R_CONS = "Conservation / Conservation-Recreation (§30-30) — no commercial use; all prohibited."
R_OB = "Office Building district (§30-404.4) — offices/research labs only; no self-storage/warehouse; li prohibited."
R_BUS = "Business district (§30-404.3) — retail/office; no self-storage/warehouse; prohibited."
R_RES = "Residential / Affordable Housing district — no storage/warehouse; all prohibited."

ROS_R = [
    ("RM","R/M Research/Manufacturing","conditional","conditional","permitted","prohibited",0.82,R_RM),
    ("C","C Conservation","prohibited","prohibited","prohibited","prohibited",0.90,R_CONS),
    ("CR","C-R Conservation-Recreation","prohibited","prohibited","prohibited","prohibited",0.90,R_CONS),
    ("OB-2","OB-2 Office Building","prohibited","prohibited","prohibited","prohibited",0.86,R_OB),
    ("OB-3","OB-3 Office Building","prohibited","prohibited","prohibited","prohibited",0.86,R_OB),
    ("B-1","B-1 Business","prohibited","prohibited","prohibited","prohibited",0.86,R_BUS),
    ("B-2","B-2 Business","prohibited","prohibited","prohibited","prohibited",0.86,R_BUS),
    ("R-1","R-1 Residence","prohibited","prohibited","prohibited","prohibited",0.90,R_RES),
    ("R-2","R-2 Residence","prohibited","prohibited","prohibited","prohibited",0.90,R_RES),
    ("R-3","R-3 Residence","prohibited","prohibited","prohibited","prohibited",0.90,R_RES),
    ("R-4","R-4 Residence","prohibited","prohibited","prohibited","prohibited",0.90,R_RES),
    ("R-13/AH-7","R-13/AH-7 Affordable Housing","prohibited","prohibited","prohibited","prohibited",0.88,R_RES),
]
ROS_CITE = cite([Q_ROS_RM, Q_ROS_PROH], "Ch. 30", ROS_ORD)

TOWNS = [
    (LIV, LIV_SUB, LIV_CITE, LIV_R),
    (MIL, MIL_SUB, MIL_CITE, MIL_R),
    (ROS, ROS_SUB, ROS_CITE, ROS_R),
]

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
        for muni, sub, cites, rows in TOWNS:
            for zc, zn, ss, mw, li, lgc, conf, note in rows:
                await con.execute(SQL, JID, zc, zn, muni, ss, mw, li, lgc,
                                  json.dumps(cites), sub, conf, note)
        for muni, *_ in TOWNS:
            rr = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
                light_industrial::text li, luxury_garage_condo::text lgc, confidence conf, human_reviewed hr
                FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
                ORDER BY (self_storage::text IN ('permitted','conditional')) DESC, zone_code""", JID, muni)
            print(f"\nCATCH #42 — {muni}: {len(rr)} rows")
            for r in rr:
                mark = " <== NEEDLE" if r["ss"] in ("permitted", "conditional") else ""
                print(f"  {r['zone_code']:11} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['conf']} hr={r['hr']}{mark}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
