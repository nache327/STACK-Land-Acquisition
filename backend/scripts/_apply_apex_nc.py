"""Apex NC (in Wake jid b05b7317…) — Stage-4 verdicts. Apex UDO Table 4.2.2 Use Table.

Wake muni bind applied Apex zoning (Phase-5). Ring done. municipality='Apex'. #37 verbatim: Apex
UDO §4.2 Table 4.2.2 Use Table (apexnc.org DocumentCenter/View/549 PDF), "Self-service storage" row
(use §4.3.5.G.31; supplemental standards §4.4.5.G.14). Column-aligned by pdfplumber x-coordinate;
VALIDATED vs the "Retail sales, general" row (P at PC/TF/LI/PUD).

"Self-service storage" row: **P (permitted) in TF (x≈498) and LI (x≈521) columns ONLY**; all other
district columns blank -> not permitted. (The "**" at x≈668 is the footnote/supplemental-standards
column, not a district. §4.4.5.G.14 = the self-service-storage supplemental standard.)

Verdicts (municipality='Apex'; -CZ/-CU = conditional-zoning/use overlays on the same base district):
  LI / LI-CU / LI-CZ (Light Industrial): self_storage / mini_warehouse = PERMITTED (Table 4.2.2
    "Self-service storage" = P in LI), light_industrial PERMITTED.
  TF / TF-CZ: self_storage / mini_warehouse = PERMITTED (P in TF), light_industrial prohibited
    (TF is a commercial/flex district — retail + self-storage permitted, not general light industry).
  PC / PC-CU / PC-CZ, CB / CB-CU, O&I / O&I-CZ / O&I-CU: self_storage / mini_warehouse = PROHIBITED
    (blank in the Self-service storage row — not permitted). light_industrial prohibited.
  lgc prohibited. (PUD-CZ excluded — parcel-specific conditional zoning, not district-groundable.)

Needle: LI+LI-CU (9 in-ring) + TF+TF-CZ (7 in-ring) ≈ 16.
Run: python scripts/_apply_apex_nc.py
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent)); sys.path.insert(0, str(Path(__file__).parent))
import asyncpg
from _db import get_sync_dsn

JID = "b05b7317-b412-492c-a56c-433d447d17bf"
MUNI = "Apex"
ORD_ = "Town of Apex NC UDO §4.2 Table 4.2.2 Use Table (apexnc.org, DocumentCenter/View/549); 'Self-service storage' row (§4.3.5.G.31 / §4.4.5.G.14)"
_LI = ('UDO Table 4.2.2 "Self-service storage" row = "P" in the LI (Light Industrial) column '
       '(pdfplumber x-aligned, validated vs "Retail sales, general" P at PC/TF/LI/PUD). Permitted with '
       'supplemental standards §4.4.5.G.14.')
_TF = ('UDO Table 4.2.2 "Self-service storage" row = "P" in the TF column (x-aligned). Permitted with '
       'supplemental standards §4.4.5.G.14.')
_NO = ('UDO Table 4.2.2 "Self-service storage" row is blank in this district column (only TF and LI = P) '
       '-> self-storage not a permitted use.')
V = {
 "LI":    ("LI Light Industrial","permitted","permitted","permitted","prohibited",0.88,_LI),
 "LI-CU": ("LI Light Industrial (CU)","permitted","permitted","permitted","prohibited",0.88,_LI),
 "LI-CZ": ("LI Light Industrial (CZ)","permitted","permitted","permitted","prohibited",0.88,_LI),
 "TF":    ("TF district","permitted","permitted","prohibited","prohibited",0.85,_TF),
 "TF-CZ": ("TF district (CZ)","permitted","permitted","prohibited","prohibited",0.85,_TF),
 "PC":    ("PC","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "PC-CU": ("PC (CU)","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "PC-CZ": ("PC (CZ)","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "CB":    ("CB","prohibited","prohibited","prohibited","prohibited",0.83,_NO),
 "CB-CU": ("CB (CU)","prohibited","prohibited","prohibited","prohibited",0.83,_NO),
 "O&I":   ("O&I Office/Institutional","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "O&I-CZ":("O&I Office/Institutional (CZ)","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "O&I-CU":("O&I Office/Institutional (CU)","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
}
SQL = """
INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage,
 mini_warehouse, light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
 human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
 $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage,
 mini_warehouse=EXCLUDED.mini_warehouse, light_industrial=EXCLUDED.light_industrial,
 luxury_garage_condo=EXCLUDED.luxury_garage_condo, citations=EXCLUDED.citations,
 cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence, human_reviewed=true,
 classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""
async def main():
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=180)
    try:
        assert "Wake" in (await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID))
        assert MUNI in {r["city"] for r in await con.fetch("SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2", JID, MUNI)}
        present = {r["z"] for r in await con.fetch("SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2 AND zoning_code IS NOT NULL", JID, MUNI)}
        await con.execute("SET statement_timeout='180s'"); n=0
        for zc,(zn,ss,mw,li,lgc,conf,q) in V.items():
            if zc not in present: continue
            cites=json.dumps([{"ordinance":ORD_,"section":"UDO Table 4.2.2","quote":q}])
            await con.execute(SQL,JID,zc,zn,MUNI,ss,mw,li,lgc,cites,"UDO Table 4.2.2",conf,f"Apex {zc} ({zn}) ss={ss} mw={mw} li={li}"); n+=1
        print(f"applied {n} Apex rows")
        j=await con.fetchrow("SELECT count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000) needles FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 WHERE p.jurisdiction_id=$1::uuid AND p.city=$2",JID,MUNI)
        print(f"Apex wealth-gated self-storage needles: {j['needles']}")
    finally:
        await con.close()
asyncio.run(main())
