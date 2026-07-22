"""Backfill parcels.owner_mailing_address / owner_mailing_csz from raw JSONB.

Bucket A of the 2026-07-22 owner-mailing feasibility audit: the owner's MAILING
address (distinct from the situs `address`) is already sitting in `parcels.raw`
for the sources whose ingest preserved the full source row. This promotes it into
the two 0053 columns — zero re-pull, zero vendor cost, pure SQL.

JOIN INTEGRITY: `raw` is the parcel's own 1:1 source row, so the mailing field is
read off the SAME row as owner/situs — no cross-row join, no mis-mail risk. Verified
by --dry-run sample output (compare owner + situs + composed mailing per parcel).

Idempotent: COALESCE only fills columns that are currently NULL, so re-runs are
safe and a later re-pull (Bucket B) can still overwrite NULLs it didn't touch.
owner_name is filled ONLY where currently NULL (never overwrites a grounded name).

Raw values carry pandas `'nan'` / JSON null / whitespace sentinels — all normalized
to NULL before composing.

    python scripts/_backfill_parcel_owner_mailing.py            # dry-run: sample rows + coverage
    python scripts/_backfill_parcel_owner_mailing.py --apply
"""
from __future__ import annotations

import argparse
import asyncio

import asyncpg
from _db import get_sync_dsn

# jid-prefix -> (name, owner_keys, addr_keys(street), csz_keys(city/state/zip)).
# addr/csz keys are concat_ws-joined (empties dropped); owner_keys joined with ' & '.
# Verified against real raw samples 2026-07-22.
SOURCES: dict[str, tuple] = {
    "7f5293ff": ("Chester County, PA",   ["OWN1", "OWN2"], ["ADDR1"], ["ADDR2", "ADDR3", "ZIP1"]),
    "7ad622d4": ("Contra Costa Cnty, CA", [],              ["N_STR_NBR", "N_STR_NM", "N_STR_SUF", "N_APT_NBR"], ["N_CTY_ST", "N_ZIP"]),
    "9c039328": ("Middlesex County, NJ", ["OWNER_NAME"],  ["ST_ADDRESS"], ["CITY_STATE", "ZIP_CODE"]),
    "703d95b4": ("Monmouth County, NJ",  ["OWNER_NAME"],  ["ST_ADDRESS"], ["CITY_STATE", "ZIP_CODE"]),
    "9fd6996b": ("Greenwood Village, CO", ["Owner"],       ["Owner_Mail_Address"], ["Owner_City_State_Zip"]),
    "307285f8": ("Franklin, TN",         ["OWNER_1", "OWNER_2"], ["OWN_STREET"], ["OWN_CITY", "OWN_STATE", "OWN_ZIP"]),
    "e0df78b2": ("Brentwood, TN",        ["OWNER_1", "OWNER_2"], ["OWN_STREET"], ["OWN_CITY", "OWN_STATE", "OWN_ZIP"]),
    "3e706886": ("Westchester Cnty, NY", ["PRIMARY_OWNER"], ["MAIL_ADDR", "PO_BOX"], ["MAIL_CITY", "MAIL_STATE", "MAIL_ZIP"]),
    "4208af9b": ("Hingham, MA",          ["OWNER1"],      ["OWN_ADDR"], ["OWN_CITY", "OWN_STATE", "OWN_ZIP"]),
    "66230887": ("Fairfield County, CT", ["Owner", "Co_Owner"], ["Mailing_Address"], ["Mailing_City", "Mailing_State"]),
    "9bbffb2b": ("Stamford, CT",         ["Owner", "Co_Owner"], ["Mailing_Address"], ["Mailing_City", "Mailing_State"]),
    "e5406ad0": ("Greenwich, CT",        ["Owner", "Co_Owner"], ["Mailing_Address"], ["Mailing_City", "Mailing_State"]),
    "a5d68bcd": ("Atlanta-Buckhead, GA", ["Owner"],       ["OwnerAddr1"], ["OwnerAddr2"]),
    "b49ac34f": ("Sandy Springs, GA",    ["Owner"],       ["OwnerAddr1"], ["OwnerAddr2"]),
    "524b1948": ("Highlands Ranch, CO",  ["Account_Fact_OWNER_NAME"], ["Account_Fact_MAILING_ADDRESS_LI"],
                 ["Account_Fact_MAILING_CITY_NAME", "Account_Fact_MAILING_STATE", "Account_Fact_MAILING_ZIP_CODE"]),
    "c9af9445": ("South Charlotte, NC",  ["ownname", "ownname2"], ["mailadd"], ["mcity", "mstate", "mzip"]),
}

# normalized single-key expr: trims, collapses whitespace, nulls the sentinels.
def _norm(key: str) -> str:
    return (
        "NULLIF(CASE WHEN lower(btrim(coalesce(raw->>'{k}',''))) "
        "IN ('','nan','null','none','n/a','.') THEN NULL "
        "ELSE btrim(regexp_replace(raw->>'{k}', '\\s+', ' ', 'g')) END, '')"
    ).format(k=key)


def _concat(keys: list[str], sep: str) -> str:
    if not keys:
        return "NULL"
    parts = ", ".join(_norm(k) for k in keys)
    return f"NULLIF(btrim(concat_ws('{sep}', {parts})), '')"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    c = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0)
    await c.execute("SET statement_timeout = 0")

    grand = {"addr": 0, "csz": 0, "own": 0, "rows": 0}
    for pref, (name, owner_keys, addr_keys, csz_keys) in SOURCES.items():
        jid = await c.fetchval("SELECT id FROM jurisdictions WHERE id::text LIKE $1", pref + "%")
        if jid is None:
            print(f"!! {name}: jurisdiction {pref} not found — skipping")
            continue
        addr_e = _concat(addr_keys, " ")
        csz_e = _concat(csz_keys, " ")
        own_e = _concat(owner_keys, " & ")

        if not args.apply:
            # show 3 composed samples for eyeball JOIN-integrity + coverage
            rows = await c.fetch(
                f"SELECT apn, address AS situs, {own_e} AS m_owner, "
                f"{addr_e} AS m_addr, {csz_e} AS m_csz "
                f"FROM parcels WHERE jurisdiction_id=$1 AND raw <> '{{}}'::jsonb "
                f"AND raw IS NOT NULL AND {addr_e} IS NOT NULL LIMIT 3", jid)
            cov = await c.fetchrow(
                f"SELECT count(*) n, count(*) FILTER (WHERE {addr_e} IS NOT NULL) a "
                f"FROM (SELECT raw, address FROM parcels WHERE jurisdiction_id=$1 "
                f"AND raw <> '{{}}'::jsonb AND raw IS NOT NULL LIMIT 6000) t", jid)
            pct = (100.0 * cov["a"] / cov["n"]) if cov["n"] else 0.0
            print(f"\n=== {name}  (mailing present {pct:.0f}% of sample, n={cov['n']}) ===")
            for r in rows:
                print(f"  owner={r['m_owner']!r}")
                print(f"    situs={r['situs']!r}")
                print(f"    MAIL = {r['m_addr']!r} | {r['m_csz']!r}")
            continue

        # apply: COALESCE-fill only NULLs, scoped to this jurisdiction's real raw rows
        own_set = f"owner_name = COALESCE(owner_name, {own_e})," if owner_keys else ""
        res = await c.execute(
            f"UPDATE parcels SET "
            f"{own_set} "
            f"owner_mailing_address = COALESCE(owner_mailing_address, {addr_e}), "
            f"owner_mailing_csz = COALESCE(owner_mailing_csz, {csz_e}) "
            f"WHERE jurisdiction_id=$1 AND raw <> '{{}}'::jsonb AND raw IS NOT NULL", jid)
        counts = await c.fetchrow(
            "SELECT count(*) FILTER (WHERE owner_mailing_address IS NOT NULL) a, "
            "count(*) FILTER (WHERE owner_mailing_csz IS NOT NULL) z, "
            "count(*) FILTER (WHERE owner_name IS NOT NULL) o "
            "FROM parcels WHERE jurisdiction_id=$1", jid)
        print(f"{name:24} {res:>14}  -> mail_addr={counts['a']:>7}  csz={counts['z']:>7}  owner={counts['o']:>7}")
        grand["addr"] += counts["a"]; grand["csz"] += counts["z"]; grand["own"] += counts["o"]

    if args.apply:
        print(f"\nTOTAL parcels with mailing address across Bucket A: {grand['addr']:,}")
    else:
        print("\ndry-run — inspect composed MAIL lines above, then re-run with --apply")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
