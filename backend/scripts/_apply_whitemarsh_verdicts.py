"""Whitemarsh Township (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in pasted Whitemarsh Zoning Ch.116: HVY §116-155, LIM/LIM-X §116-144, CLI §116-120,
CLI-X §116-128, CR-H/CR-L §116-104. asyncpg human-UPSERT (catch #29), municipality='Whitemarsh Township'.
Catch #38: Whitemarsh Township, Montgomery County PA (Lafayette Hill/Flourtown). Idempotent.

  HVY Heavy Industrial -> PERMITTED (0.90). §116-155.A "any lawful purpose" by-right EXCEPT an enumerated
      noxious list + "Retail commercial"; self-storage not excluded -> catch-all permitted (same basis as
      Upper Merion HI §165-153). 8 SN-pass.
  LIM Limited Industrial -> CONDITIONAL (0.75). Warehouse is accessory-only (§116-144.A(15)); self-storage
      not by-right, BUT A(21) "any industrial use not specifically excluded ... when authorized as a
      special exception" + storage-flavored by-right uses (A(2) cold storage/distribution, A(14) commercial-
      vehicle garage) make a self-storage facility admissible by special exception. §116-155 cross-ref
      excludes only noxious + retail, not self-storage. -> conditional (needle-eligible). 9 SN-pass.
  CLI Campus-Type Limited Industrial -> PROHIBITED (0.90). §116-120 office/lab/light-mfg; F warehousing
      ONLY of on-site-manufactured products; G special-exception catch-all EXPLICITLY excludes "general
      public warehouse" + truck terminal. Self-storage = general public storage -> excluded -> prohibited.
      (catch #37: "industrial-NAMED but office/lab + public-warehouse-excluded" — confirmed the trap.)
  CLI-X Modified Campus-Type Limited Industrial -> PROHIBITED (0.90). §116-128 identical to CLI.
  CR-H Commercial Retail-High -> PROHIBITED (0.85). §116-104.A retail/office/bank; no storage; silence.
  CR-L Commercial Retail -> PROHIBITED (0.82). §116-104.B CR-H uses + trade shops/labs; A(6) SE catch-all
      limited to retail/wholesale/customer-service (not storage); no self-storage; silence.

Armed pool = HVY(8 permitted) + LIM(9 conditional) = 17. CLI+CLI-X (27 SN-pass) prohibited (the trap).
EX Extraction (1 SN-pass, quarrying) not pasted -> not verdicted (negligible + wrong use class).

Run: python scripts/_apply_whitemarsh_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Whitemarsh Township"

VERDICTS = {
    "HVY": ("permitted", "permitted", 0.90, "HVY Heavy Industrial",
            "§116-155.A 'any lawful purpose' by-right except enumerated noxious uses + retail commercial; self-storage not excluded -> catch-all permitted"),
    "LIM": ("conditional", "permitted", 0.75, "LIM Limited Industrial",
            "§116-144.A(21) 'any industrial use not specifically excluded' as special exception + storage-flavored by-right uses (A(2) cold storage/distribution, A(14) commercial-vehicle garage); warehouse accessory-only (A(15)) so not by-right -> conditional via SE; §116-155 excludes only noxious+retail, not self-storage"),
    "CLI": ("prohibited", "permitted", 0.90, "CLI Campus-Type Limited Industrial",
            "§116-120: office/lab/light-mfg; F warehousing ONLY of on-site-manufactured products; G SE catch-all EXPLICITLY excludes 'general public warehouse' + truck terminal -> self-storage (general public storage) prohibited"),
    "CLI-X": ("prohibited", "permitted", 0.90, "CLI-X Modified Campus-Type Limited Industrial",
              "§116-128 identical to CLI (office/lab/light-mfg; F ancillary warehouse only; G excludes general public warehouse) -> self-storage prohibited"),
    "CR-H": ("prohibited", "unclear", 0.85, "CR-H Commercial Retail-High",
             "§116-104.A retail/personal-service/office/bank/bakery; no warehouse/storage/self-storage; silence rule"),
    "CR-L": ("prohibited", "unclear", 0.82, "CR-L Commercial Retail",
             "§116-104.B CR-H uses + trade shops/labs/funeral/gas(SE); A(6) SE catch-all limited to retail/wholesale/customer-service (not storage); no self-storage; silence rule"),
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
    url = settings.database_url.replace(":6543/", ":5432/").replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='90s'")
        for zc, (ss, li, conf, zname, cite) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Whitemarsh Township Zoning Ch. 116",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Whitemarsh {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Whitemarsh Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
