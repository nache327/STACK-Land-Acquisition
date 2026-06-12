"""Apply Tewksbury Township (Hunterdon NJ) Article VII verdicts — ALL PROHIBITED.

Ground-truthed from the Tewksbury Township Land Development Ordinance Article VII
(§§709-718), pasted by Nache 2026-06-12. Every Tewksbury district prohibits self-storage:
the business/office/mixed districts (VB §716, VO §716.1, RO/MXD §717) permit only
retail/office/research uses and do NOT name warehouse as a principal by-right use, so the
warehouse->self_storage conditional convention does NOT fire (silence rule). PM is the
Piedmont CONSERVATION district (false-friend catch #18), not manufacturing. All remaining
districts are residential/agricultural.

Writes muni-specific rows (municipality='Tewksbury township') so the muni-aware scoring join
resolves Tewksbury exactly. Reverse-direction discipline (#13): ON CONFLICT DO UPDATE with
human_reviewed=true so a hand verdict wins over any pre-existing factory/county-default row.
Idempotent. Run: python scripts/_apply_tewksbury.py  (reads DATABASE_URL from backend/.env)
"""
import asyncio
import json

import asyncpg

JUR = "e8612f49-218b-48cc-9eb0-a1dd90cf583d"  # Hunterdon County, NJ
MUNI = "Tewksbury township"
ART = "Tewksbury Township Land Development Ordinance, Article VII"

# zone_code -> (zone_name, cited_section, confidence, basis)
VERDICTS = {
    "VB":     ("Village Business",            "§716.B",   0.92, "Permitted principal uses = retail/restaurant/office (first floor + basement) only; warehouse/storage not named -> silence rule."),
    "VO":     ("Village Office",              "§716.1.B", 0.92, "Permitted principal uses = business/professional office + banks + post offices only -> silence rule."),
    "RO/MXD": ("Research Office / Mixed Use",  "§717.B",   0.85, "Permitted principal uses = office, research, banks, restaurants, utility; warehouse NOT permitted by-right -> convention does not fire -> silence rule."),
    "PM":     ("Piedmont (Conservation)",     "§710.2.B", 0.95, "Piedmont CONSERVATION district (1 home/5ac), agricultural/residential + kennels; NOT manufacturing (false-friend catch #18)."),
    "HL":     ("Highlands",                   "§709.B",   0.95, "12-acre residential/agricultural; principal uses = ag, SFD, civic, worship, schools, affordable housing. No commercial/industrial."),
    "LT":     ("Lamington",                   "§710.B",   0.95, "10-acre residential/agricultural; same use set as HL."),
    "FP":     ("Farmland Preservation",       "§710.1.B", 0.95, "7-acre farmland preservation; residential/agricultural use set."),
    "VR":     ("Village Residential",         "Art. VII", 0.90, "Residential district -> no commercial/industrial principal use (silence rule)."),
    "SO":     ("South Oldwick",               "Art. VII", 0.90, "Residential district -> silence rule."),
    "R-1.5":  ("Residential 1.5ac",           "Art. VII", 0.95, "Residential district -> silence rule."),
    "TH-V":   ("Townhouse-Village",           "Art. VII", 0.90, "Residential district -> silence rule."),
    "R-2":    ("Residential R-2",             "Art. VII", 0.95, "Residential district -> silence rule."),
}

SQL = """
INSERT INTO zone_use_matrix
    (jurisdiction_id, zone_code, zone_name, municipality,
     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
     citations, cited_subsection, confidence, human_reviewed, classification_source, notes,
     created_at, updated_at)
VALUES
    ($1, $2, $3, $4,
     'prohibited','prohibited','prohibited','prohibited',
     $5::jsonb, $6, $7, true, 'human', $8, now(), now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality, '')) WHERE deleted_at IS NULL
DO UPDATE SET
    self_storage='prohibited', mini_warehouse='prohibited',
    light_industrial='prohibited', luxury_garage_condo='prohibited',
    citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
    confidence=EXCLUDED.confidence, human_reviewed=true,
    classification_source='human', zone_name=EXCLUDED.zone_name,
    notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        before = await con.fetchval(
            "SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL",
            JUR, MUNI)
        async with con.transaction():
            for zc, (name, sec, conf, basis) in VERDICTS.items():
                cites = json.dumps([{"ordinance": ART, "section": sec, "basis": basis}])
                note = f"{name}: self_storage prohibited ({sec}). {basis}"
                await con.execute(SQL, JUR, zc, name, MUNI, cites, sec, conf, note)
        after = await con.fetchval(
            "SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed",
            JUR, MUNI)
        print(f"Tewksbury muni-specific rows before={before}, human_reviewed after={after} (applied {len(VERDICTS)} zones, all prohibited)")
        # verify every Tewksbury parcel now resolves to a muni-specific prohibited verdict
        unresolved = await con.fetchval("""
            SELECT COUNT(*) FROM parcels p
            LEFT JOIN zone_use_matrix z ON z.jurisdiction_id=p.jurisdiction_id
                AND z.zone_code=p.zoning_code AND z.municipality=$2 AND z.deleted_at IS NULL
            WHERE p.jurisdiction_id=$1 AND p.city ILIKE 'tewksbury%' AND z.id IS NULL
        """, JUR, MUNI)
        print(f"Tewksbury parcels with NO muni-specific verdict row (should be 0): {unresolved}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
