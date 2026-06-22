"""East Whiteland Township (Chester County PA) — self-storage verdicts.

Grounded in East Whiteland Zoning Ch. 200 Tables of Permitted Uses (Attachments 6/8/10),
pasted by Nache. Self-storage is EXPLICITLY named in ONE district only:

  Attachment 8 (Industrial, I): "Self-service storage facility = P" + "Storage facility = P"
    -> I = self_storage PERMITTED (0.98). Also full manufacturing/fab/processing P -> light_industrial permitted.

  Attachment 6 (Mixed-Use: VMX/FC/ROC/O/BP/O/BPS/PO/GVR): NO self-service storage use; only
    "Warehouse (accessory)" (accessory-only, does NOT trigger the storage convention).
    -> all Mixed-Use = self_storage PROHIBITED (silence). O/BP + O/BPS have "Light manufacturing P"
       -> light_industrial permitted; the rest unclear.
    NOTE: O/BP (186 parc, 118 sized, 6 listings) + FC (149, 52, 10 listings) — the heuristic recon's
    "top target" — are PROHIBITED here. The storage zone is I, which has 0 current listings.

  Attachment 10 (Institutional: INS/NS/C): educational/religious/hospital/cemetery; no storage
    -> PROHIBITED (silence).

  Residential / open-space (R-1/R-2/R-3/RMH/RM/OS/ROC-R/RRD/FR): not in the commercial/industrial/
    institutional tables; residential/open-space class -> PROHIBITED (silence rule).

Muni-specific municipality='East Whiteland Township' (catch #28/#29 — asyncpg human-UPSERT, NOT
factory_safe_write). Idempotent. Run: python scripts/_apply_east_whiteland.py
"""
import asyncio
import json

import asyncpg

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"  # Chester County, PA
MUNI = "East Whiteland Township"

# zone -> (self_storage, light_industrial, confidence, cite)
T8 = "Attachment 8 (Industrial I use table)"
T6 = "Attachment 6 (Mixed-Use use table)"
T10 = "Attachment 10 (Institutional use table)"
VERDICTS = {
    "I":     ("permitted",  "permitted", 0.98, f"{T8}: 'Self-service storage facility'=P + 'Storage facility'=P"),
    "O/BP":  ("prohibited", "permitted", 0.95, f"{T6}: no self-service storage use; Warehouse accessory-only; Light manufacturing=P; silence rule for storage"),
    "O/BPS": ("prohibited", "permitted", 0.95, f"{T6}: no self-service storage use; Warehouse accessory-only; Light manufacturing=P; silence rule for storage"),
    "FC":    ("prohibited", "unclear",   0.95, f"{T6}: Mixed-Use; no self-service storage / no principal warehouse; silence rule"),
    "VMX":   ("prohibited", "unclear",   0.95, f"{T6}: Mixed-Use; no self-service storage; silence rule"),
    "ROC":   ("prohibited", "unclear",   0.95, f"{T6}: Mixed-Use; no self-service storage; silence rule"),
    "ROC/R": ("prohibited", "unclear",   0.90, "§200-35 ROC/R residential; no self-service storage; silence rule"),
    "PO":    ("prohibited", "unclear",   0.95, f"{T6}: Mixed-Use (office); no self-service storage; silence rule"),
    "INS":   ("prohibited", "unclear",   0.95, f"{T10}: institutional; no self-service storage; silence rule"),
    "NS":    ("prohibited", "unclear",   0.95, f"{T10}: institutional; no self-service storage; silence rule"),
    "C":     ("prohibited", "unclear",   0.95, f"{T10}: institutional; no self-service storage; silence rule"),
    "R-1":   ("prohibited", "unclear",   0.90, "Residential district; self-storage not a permitted use; silence rule"),
    "R-2":   ("prohibited", "unclear",   0.90, "Residential district; self-storage not a permitted use; silence rule"),
    "R-3":   ("prohibited", "unclear",   0.90, "Residential district; self-storage not a permitted use; silence rule"),
    "RMH":   ("prohibited", "unclear",   0.90, "Residential (mobile home) district; silence rule"),
    "RM":    ("prohibited", "unclear",   0.90, "Residential (multifamily) district; silence rule"),
    "OS":    ("prohibited", "unclear",   0.90, "Open space district; silence rule"),
    "RRD":   ("prohibited", "unclear",   0.88, "Residential district; silence rule"),
    "FR":    ("prohibited", "unclear",   0.88, "Residential/rural district; silence rule"),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$8,$4::use_permission_enum,$4::use_permission_enum,
  $5::use_permission_enum,'unclear',$6::jsonb,$7,$9,true,'human',$10,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, citations=EXCLUDED.citations,
  cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc, (ss, li, conf, cite) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "East Whiteland Township Zoning Ch. 200",
                                 "section": cite.split(":")[0], "basis": f"self_storage={ss} in {zc} per {cite}"}])
            note = f"{zc}: self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"East Whiteland {zc}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code",
            JID, MUNI)
        print(f"applied {len(rows)} East Whiteland Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:7} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
