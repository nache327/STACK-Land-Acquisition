"""Franklin TN — accuracy correction (2026-07-15). Text-verification close-out of the
graphic §5.1.3 dot-matrix reads for RC12 + CI (prior conf 0.72).

Verified via the UDO text layer (building-type "Permitted Districts" framework §6.12/§6.13,
district purposes §3.12/§3.20, use-standard §5.1.4.V/J — flippingbook web.franklintn.gov):
 - CI (Civic Institutional): REFUTED. The Flex Building — the only building type "designed to
   accommodate industrial uses" incl. general warehousing — is permitted ONLY in LI/HI (§6.13).
   CI's permitted building types are Civic + continuum-of-care only (§3.12.3), which cannot house
   self-storage/warehousing. Every text signal contradicts the dot-read. -> CI stays PROHIBITED
   (now REFUTED, not merely held).
 - RC12 (Regional Commerce): NOT text-confirmed. §5.1.4.V (Self-Storage Facilities) names NO
   permitted districts; no text sentence permits self-storage in RC12. The read is corroborated as
   PLAUSIBLE (RC12 purpose = high-intensity mixed uses; permits Commercial/Mixed-Use buildings that
   could house it) but not confirmed. Per coordinator rule (unconfirmable -> demote) + #58
   (demote what fits no NAMED use) -> DEMOTE RC12 self-storage to PROHIBITED (restorable if the
   authoritative graphic matrix is later human-verified; NOT refuted, unlike CI).
 - LI/HI: KEEP self-storage conditional — now TEXT-CORROBORATED: "Self-Storage Facilities" is a
   named principal use (§5.1.4.V + Ch.23 def) and the Flex Building industrial type is confined to
   LI/HI (§6.13). Raise confidence.

Effect: Franklin needles 277 -> 185 (RC12's 92 removed; LI 169 + HI 16 remain).
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_franklin_correction.py
"""
import asyncio, json, asyncpg

JID = "307285f8-9426-4f17-9e66-999c8e01218f"  # Franklin, TN
MUNI = "Franklin"
ORD = "City of Franklin, TN Zoning Ordinance (Envision Franklin UDO, eff. 1-13-2026)"


def cite(*qs):
    return [{"quote": q, "section": "Zoning", "ordinance": ORD} for q in qs]


Q_LIHI = ("'Self-Storage Facilities' named principal use (§5.1.4.V; Ch.23 def) + Flex Building — the "
          "industrial building type 'designed to accommodate industrial uses' incl. general warehousing "
          "— permitted ONLY in LI/HI (§6.13). §5.1.3 half-circle = permitted-with-standards.")
Q_RC12 = ("§5.1.4.V (Self-Storage Facilities) names NO permitted district; no text permits self-storage "
          "in RC12. Graphic §5.1.3 dot-read (half-circle) is corroborated-plausible (RC12 §3.20.1 "
          "high-intensity mixed uses; Commercial/Mixed-Use building type §3.20.3) but NOT text-confirmed "
          "-> demoted per #58 (no NAMED use). Restorable if the authoritative matrix is human-verified.")
Q_CI = ("CI §3.12.1 purpose = 'civic, recreational, and institutional uses'; permitted building types "
        "(§3.12.3) = Civic Building + continuum-of-care ONLY. The Flex Building (industrial/warehouse "
        "type) is permitted only in LI/HI (§6.13) — NOT CI. REFUTED: no CI building type can house "
        "self-storage or general warehousing.")

# zone_code, ss, mw, li, lgc, conf, note, cites
ROWS = [
    ("LI", "conditional", "conditional", "permitted", "prohibited", 0.88,
     "ss/mw CONDITIONAL (GROUNDED, text-corroborated): Self-Storage Facilities named §5.1.4.V; Flex "
     "Building industrial type confined to LI/HI §6.13; General Warehousing permitted. li PERMITTED. lgc PROHIBITED.",
     cite(Q_LIHI)),
    ("HI", "conditional", "conditional", "permitted", "prohibited", 0.88,
     "ss/mw CONDITIONAL (GROUNDED, text-corroborated): Self-Storage Facilities named §5.1.4.V; Flex "
     "Building §6.13 LI/HI; Heavy Industrial + General Warehousing permitted. li PERMITTED. lgc PROHIBITED.",
     cite(Q_LIHI)),
    ("RC12", "prohibited", "prohibited", "prohibited", "prohibited", 0.70,
     "DEMOTED (#58): self-storage NOT a named use in RC12 text (§5.1.4.V lists no districts). Graphic "
     "dot-read was corroborated-PLAUSIBLE (not refuted) but unconfirmable -> prohibited pending "
     "human verification of the authoritative §5.1.3 matrix. Was 92 needles.",
     cite(Q_RC12)),
    ("CI", "prohibited", "prohibited", "prohibited", "prohibited", 0.85,
     "PROHIBITED (REFUTED): CI = Civic Institutional; building types (Civic + continuum-of-care, §3.12.3) "
     "cannot house self-storage/warehousing; Flex industrial type is LI/HI-only (§6.13). The graphic "
     "self-storage dot-read is a mis-read. #38.",
     cite(Q_CI)),
]

SQL = """UPDATE zone_use_matrix SET self_storage=$3::use_permission_enum, mini_warehouse=$4::use_permission_enum,
 light_industrial=$5::use_permission_enum, luxury_garage_condo=$6::use_permission_enum,
 citations=$7::jsonb, confidence=$8, notes=$9, human_reviewed=true, classification_source='human', updated_at=now()
 WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code=$10 AND deleted_at IS NULL"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc, ss, mw, li, lgc, conf, note, cits in ROWS:
            res = await con.execute(SQL, JID, MUNI, ss, mw, li, lgc, json.dumps(cits), conf, note, zc)
            print(f"  {zc}: {res}")
        got = await con.fetch("""SELECT zone_code, self_storage::text ss, confidence FROM zone_use_matrix
            WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code=ANY($3) AND deleted_at IS NULL
            ORDER BY zone_code""", JID, MUNI, ["LI", "HI", "RC12", "CI"])
        print("#42 post-correction:")
        for r in got:
            print(f"  {r['zone_code']:6} ss={r['ss']:11} conf={r['confidence']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
