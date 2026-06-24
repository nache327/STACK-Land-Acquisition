"""Wave-6 apply-script generator.

Pre-authors 23 _apply_<polygon>_<state>.py scripts following the
backend/scripts/_apply_winnetka_il.py shape (PR #356/#367 precedent).

Per Master 2026-06-23 ACTION 2 dispatch. Each apply script:
1. Reads its corresponding pre-stage JSON from backend/data/wave6_pre_stage/
2. Queries prod /api/admin/op5/uncovered-zone-codes for actual zone-code
   spellings (Winnetka lesson: pre-stage R-1 → prod R1)
3. Spelling-adapts the substrate (drops/renames codes to match prod)
4. POSTs to /api/jurisdictions/{JID}/_upload-matrix-rows with
   replace_existing=False (factory_safe_write contract)
5. Verifies uncovered_count → 0
6. Triggers ONE refresh

SCOPE GUARDS (per Master):
- Pre-author only — DO NOT invoke any of the generated scripts
- Fire gated on Lane A signals (parcels.zoning_code populated + cov ≥ 70%)
- DO NOT touch factory_safe_write contract (it lives in Lane A's domain)
- Burlington trio scripts are nache hand-offs (orchestrator does not invoke)

Run: python backend/scripts/_drafts/_wave6_apply_generator.py
"""
from __future__ import annotations
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "backend" / "scripts"
DATA_DIR = REPO_ROOT / "backend" / "data" / "wave6_pre_stage"

# Verified JIDs from 2026-06-23 /api/admin/coverage probe.
# Empty string = jurisdiction NOT registered in prod yet — JID must be
# resolved at fire-time (env var or runtime query).
KNOWN_JIDS = {
    "Williamson County, TN": "ed49aa24-d744-44e5-b15c-1f778a220837",
    "Fulton County, GA":      "bb9e5176-c1e8-4221-9f2e-b27c34545f98",
    "Wake County, NC":        "b05b7317-b412-492c-a56c-433d447d17bf",
    "Fox Chapel Borough, PA": "c5e04fa4-08d7-464b-8b74-dd56fc1f3f17",
    # Westport/New Canaan/Wilton: registered under Fairfield with parcel_count > 0
    # but per-muni JID not surfaced in probe; resolve at fire-time.
    # All other wave-6 munis: NOT REGISTERED in prod yet.
}


# (output_filename, muni, state, prestage_filename, jid_key, owner)
# jid_key: matches a KNOWN_JIDS entry ONLY if the polygon IS that registered
#   jurisdiction (e.g., Fox Chapel polygon = Fox Chapel Borough jurisdiction).
# For per-muni polygons under a parent county (Brentwood under Williamson,
# Sandy Springs under Fulton, Cary under Wake, etc.) the per-muni JID is
# DIFFERENT from the parent county JID — set jid_key to the polygon's own
# name (which won't be in KNOWN_JIDS) so the script falls through to the
# env-var path and requires JID resolution at fire-time.
POLYGONS = [
    ("_apply_brentwood_tn.py",        "Brentwood",            "TN", "williamson_brentwood.json",        "Brentwood, TN (per-muni under Williamson County)",        "orchestrator"),
    ("_apply_franklin_tn.py",         "Franklin",             "TN", "williamson_franklin.json",         "Franklin, TN (per-muni under Williamson County)",         "orchestrator"),
    ("_apply_sandy_springs_ga.py",    "Sandy Springs",        "GA", "fulton_sandy_springs.json",        "Sandy Springs, GA (per-muni under Fulton County)",        "orchestrator"),
    ("_apply_atlanta_buckhead_ga.py", "Buckhead",             "GA", "fulton_buckhead.json",             "Buckhead, GA (sub-AOI under Atlanta city under Fulton)",  "orchestrator"),
    ("_apply_charlotte_nc.py",        "Charlotte",            "NC", "mecklenburg_charlotte.json",       "Charlotte, NC (per-muni under Mecklenburg County)",       "orchestrator"),
    ("_apply_pinecrest_fl.py",        "Pinecrest",            "FL", "miami_dade_pinecrest.json",        "Pinecrest, FL (per-muni under Miami-Dade County)",        "orchestrator"),
    ("_apply_westport_ct.py",         "Westport",             "CT", "fairfield_westport.json",          "Westport, CT (per-muni under Fairfield County)",          "orchestrator"),
    ("_apply_new_canaan_ct.py",       "New Canaan",           "CT", "fairfield_new_canaan.json",        "New Canaan, CT (per-muni under Fairfield County)",        "orchestrator"),
    ("_apply_wilton_ct.py",           "Wilton",               "CT", "fairfield_wilton.json",            "Wilton, CT (per-muni under Fairfield County)",            "orchestrator"),
    ("_apply_greenwood_village_co.py","Greenwood Village",    "CO", "arapahoe_greenwood_village.json",  "Greenwood Village, CO",                                   "orchestrator"),
    ("_apply_englewood_co.py",        "Englewood",            "CO", "arapahoe_englewood.json",          "Englewood, CO",                                           "orchestrator"),
    ("_apply_lake_oswego_or.py",      "Lake Oswego",          "OR", "clackamas_lake_oswego.json",       "Lake Oswego, OR",                                         "orchestrator"),
    ("_apply_summit_ut.py",           "Summit County",        "UT", "summit_park_city_corridor.json",   "Summit County, UT (unincorporated corridor)",             "orchestrator"),
    ("_apply_cary_nc.py",             "Cary",                 "NC", "wake_cary.json",                   "Cary, NC (per-muni under Wake County)",                   "orchestrator"),
    ("_apply_raleigh_nc.py",          "Raleigh",              "NC", "wake_raleigh.json",                "Raleigh, NC (per-muni under Wake County)",                "orchestrator"),
    ("_apply_north_raleigh_nc.py",    "North Raleigh",        "NC", "wake_north_raleigh.json",          "North Raleigh, NC (sub-AOI under Raleigh under Wake)",    "orchestrator"),
    ("_apply_highlands_ranch_co.py",  "Highlands Ranch",      "CO", "douglas_highlands_ranch.json",     "Highlands Ranch, CO (Douglas County CDP)",                "orchestrator"),
    ("_apply_cherry_hills_co.py",     "Cherry Hills Village", "CO", "arapahoe_cherry_hills.json",       "Cherry Hills Village, CO",                                "orchestrator"),
    ("_apply_golden_co.py",           "Golden",               "CO", "jefferson_golden.json",            "Golden, CO",                                              "orchestrator"),
    ("_apply_fox_chapel_pa.py",       "Fox Chapel Borough",   "PA", "allegheny_fox_chapel.json",        "Fox Chapel Borough, PA",                                  "orchestrator"),
    ("_apply_medford_nj.py",          "Medford township",     "NJ", "burlington_nj_medford.json",       "Medford township, NJ (per-muni under Burlington County)", "nache"),
    ("_apply_mount_laurel_nj.py",     "Mount Laurel township","NJ", "burlington_nj_mount_laurel.json",  "Mount Laurel township, NJ (per-muni under Burlington County)", "nache"),
    ("_apply_moorestown_nj.py",       "Moorestown township",  "NJ", "burlington_nj_moorestown.json",    "Moorestown township, NJ (per-muni under Burlington County)", "nache"),
]

# Apply-script template — modeled on backend/scripts/_apply_winnetka_il.py
TEMPLATE = '''"""{muni} {state} — Bergen catchall × 4 substrate matrix apply.

Pre-stage source: backend/data/wave6_pre_stage/{prestage_filename}
Owner: {owner}
Generated by: backend/scripts/_drafts/_wave6_apply_generator.py
Pattern: Bergen catchall × 4 prohibited substrate-first per halt rule.

CRITICAL — fire gate per Master 2026-06-23 dispatch:
- Lane A's Class B zoning adapter MUST RUN against prod first
- parcels.zoning_code must be populated (cov ≥ 70%)
- This script then adapts pre-stage codes to prod spellings (Winnetka
  lesson: pre-stage R-1 → prod R1) and POSTs the matrix substrate
- Substrate-first only — NO verdict-truth lifts (halted Somerset domain)

Apply workflow:
1. Query /api/admin/op5/uncovered-zone-codes for actual prod zone codes
2. Spelling-adapt pre-stage substrate to match prod (drop unmatched,
   rename hyphen-variants)
3. POST to /api/jurisdictions/{{JID}}/_upload-matrix-rows with
   replace_existing=False (factory_safe_write contract preserves
   nache's human_reviewed=true rows)
4. Verify uncovered_count → 0
5. Trigger ONE refresh

Usage:
    {jid_setup}
    python backend/scripts/{output_filename}

Exit codes: 0 = success / 1 = apply failed / 2 = JID not set / 3 = no codes to match
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

import httpx

# === CONFIGURATION ===
MUNI = "{muni}"
STATE = "{state}"

# JID resolution priority:
#   1. {jid_env_var} environment variable (set at fire-time)
#   2. KNOWN_JID hardcoded below (only if jurisdiction already registered
#      in prod per 2026-06-23 probe; otherwise empty string)
{jid_known_block}

JID = os.environ.get("{jid_env_var}") or KNOWN_JID

API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
PRESTAGE_PATH = (
    Path(__file__).resolve().parent.parent
    / "data" / "wave6_pre_stage" / "{prestage_filename}"
)
REFRESH_SOURCE = "wave6-prestage-{slug}-2026-06-23"
# === END CONFIGURATION ===


def fetch_prod_zone_codes(jid: str) -> tuple[set[str], int]:
    """Return (uncovered_zone_codes_set, total_uncovered_count)."""
    url = f"{{API_BASE}}/api/admin/op5/uncovered-zone-codes"
    params = {{"jurisdiction_id": jid, "limit": 500}}
    r = httpx.get(url, params=params, timeout=60.0)
    r.raise_for_status()
    body = r.json()
    codes = {{row["zone_code"] for row in body.get("rows", []) if row.get("zone_code")}}
    return codes, body.get("uncovered_count", 0)


def spelling_variants(code: str) -> list[str]:
    """Generate common spelling variants to try against prod (Winnetka pattern)."""
    out = [code]
    # Hyphen <-> no-hyphen (Winnetka: R-1 vs R1)
    out.append(code.replace("-", ""))
    out.append(code.replace("-", " "))
    # Period <-> no-period (e.g., R-.05 vs R-05)
    out.append(code.replace(".", ""))
    # Lowercase (rare but possible)
    out.append(code.lower())
    out.append(code.upper())
    # Strip whitespace variants
    out.append(code.replace(" ", ""))
    out.append(code.replace(" ", "-"))
    # De-duplicate while preserving order
    seen = set()
    result = []
    for v in out:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def adapt_codes(prestage_rows: list[dict], prod_codes: set[str]) -> tuple[list[dict], list[str], list[str]]:
    """Adapt pre-stage rows to match prod code spellings.
    Returns (adapted_rows, missing_pre_codes, unused_prod_codes).
    """
    adapted = []
    missing = []
    matched_prod = set()
    for row in prestage_rows:
        pre_code = row["zone_code"]
        match = None
        for variant in spelling_variants(pre_code):
            if variant in prod_codes:
                match = variant
                break
        if match is None:
            missing.append(pre_code)
            continue
        new_row = dict(row)
        new_row["zone_code"] = match
        adapted.append(new_row)
        matched_prod.add(match)
    unused = sorted(prod_codes - matched_prod)
    return adapted, missing, unused


def main() -> int:
    print(f"{{MUNI}} {{STATE}} matrix substrate apply")
    print(f"  pre-stage: {{PRESTAGE_PATH}}")
    if not JID:
        print(
            f"ERROR: JID not set. Either populate KNOWN_JID at top of file "
            f"or set env var {jid_env_var} to a jurisdiction UUID.",
            file=sys.stderr,
        )
        return 2

    print(f"  jurisdiction_id: {{JID}}")
    upload_url = f"{{API_BASE}}/api/jurisdictions/{{JID}}/_upload-matrix-rows"
    refresh_url = (
        f"{{API_BASE}}/api/admin/coverage/refresh"
        f"?jurisdiction_id={{JID}}&source={{REFRESH_SOURCE}}"
    )

    prestage_rows = json.loads(PRESTAGE_PATH.read_text())
    print(f"  pre-stage rows: {{len(prestage_rows)}}")

    print(f"\\nFetching prod uncovered codes")
    prod_codes, uncov_count = fetch_prod_zone_codes(JID)
    print(f"  uncovered_count: {{uncov_count}}")
    print(f"  distinct uncovered codes: {{len(prod_codes)}}")

    if not prod_codes:
        print(
            f"\\nNo uncovered codes in prod. Either:\\n"
            f"  (a) jurisdiction fully matrix-covered already, or\\n"
            f"  (b) parcels.zoning_code not yet populated (cov gate fail).\\n"
            f"Verify cov gate via /api/admin/coverage before re-running.",
            file=sys.stderr,
        )
        return 3

    adapted, missing, unused = adapt_codes(prestage_rows, prod_codes)
    print(f"\\nCode adaptation:")
    print(f"  adapted (matched prod): {{len(adapted)}}")
    if missing:
        print(f"  WARNING — pre-stage codes NOT found in prod: {{missing}}")
    if unused:
        print(f"  NOTE — prod codes NOT in pre-stage (substrate gap, "
              f"may need Path B re-author): {{unused}}")

    if not adapted:
        print(f"\\nNo codes matched. Substrate fully out of sync with prod.\\n"
              f"Re-author substrate using Path B pattern.", file=sys.stderr)
        return 3

    payload = {{"rows": adapted, "replace_existing": False}}
    print(f"\\nPOST {{upload_url}}")
    print(f"  rows={{len(adapted)}}  replace_existing=False  "
          f"factory_safe_write=preserves human_reviewed=true rows")
    r = httpx.post(upload_url, json=payload, timeout=120.0)
    print(f"\\nHTTP {{r.status_code}}")
    try:
        body = r.json()
        print(json.dumps(body, indent=2)[:3000])
    except Exception:
        print(r.text[:3000])

    if r.status_code != 200:
        print(f"\\nApply failed (HTTP {{r.status_code}}). NOT firing refresh.",
              file=sys.stderr)
        return 1

    # Verify uncovered_count post-apply
    print(f"\\nVerifying post-apply state")
    _, post_uncov = fetch_prod_zone_codes(JID)
    print(f"  uncovered_count post-apply: {{post_uncov}} "
          f"(was {{uncov_count}}; delta -{{uncov_count - post_uncov}})")

    # ONE refresh per polygon
    print(f"\\nPOST {{refresh_url}}")
    r3 = httpx.post(refresh_url, timeout=120.0)
    print(f"  refresh HTTP {{r3.status_code}}")

    print(f"\\nDONE. Update tracker:")
    print(f"  - coordination/lane_state.json honest_operational_count.current_api_truth += 1")
    print(f"  - docs/PHASE2_PROGRESS.md §15 entry for {{MUNI}} {{STATE}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def slugify(s: str) -> str:
    return s.lower().replace(" ", "-").replace(".", "").replace(",", "")


def env_var_for(muni: str, state: str) -> str:
    return f"{muni.upper().replace(' ', '_').replace('.', '')}_{state}_JID"


def main() -> None:
    written = []
    for output_filename, muni, state, prestage_filename, jid_key, owner in POLYGONS:
        jid_env_var = env_var_for(muni, state)
        known_jid = KNOWN_JIDS.get(jid_key, "")
        if known_jid:
            jid_known_block = f'KNOWN_JID = "{known_jid}"  # parent {jid_key} per 2026-06-23 probe'
            jid_setup = f"# JID already set in KNOWN_JID (parent {jid_key})"
        else:
            jid_known_block = (
                f'KNOWN_JID = ""  # NOT REGISTERED in prod per 2026-06-23 probe; '
                f'set {jid_env_var} env var at fire-time'
            )
            jid_setup = f"export {jid_env_var}=<jurisdiction_uuid>  # resolve from prod"

        slug = slugify(muni)
        script = TEMPLATE.format(
            muni=muni,
            state=state,
            prestage_filename=prestage_filename,
            output_filename=output_filename,
            jid_known_block=jid_known_block,
            jid_setup=jid_setup,
            jid_env_var=jid_env_var,
            slug=slug,
            owner=owner,
        )
        out_path = SCRIPTS_DIR / output_filename
        out_path.write_text(script)
        written.append((output_filename, muni, state, owner, bool(known_jid)))

    print(f"Wrote {len(written)} apply scripts to {SCRIPTS_DIR}:")
    for filename, muni, state, owner, has_jid in written:
        jid_marker = "JID-set" if has_jid else "JID-TBD"
        owner_marker = f"[{owner}]" if owner != "orchestrator" else ""
        print(f"  {filename}  ({muni}, {state})  {jid_marker} {owner_marker}")


if __name__ == "__main__":
    main()
