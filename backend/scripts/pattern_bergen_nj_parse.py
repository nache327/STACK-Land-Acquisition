"""LLM-draft per-city zone verdicts for Bergen County, NJ — Tier 1+2 sprint.

Targets (PR scope = Tier 1+2 only; Tier 3 deferred):
  - Paramus borough      (Tier 1: 96% zoning_code, 123 districts — binds now)
  - Elmwood Park borough (Tier 2: 38 districts, needs code backfill to bind)
  - Teaneck township     (Tier 2: 14 districts, needs code backfill to bind)

Workflow (mirrors Howard MD / Loudoun / Allentown sprints — LLM-draft then human
review before promote):
  1. --dry-run (DEFAULT): fetch each city's eCode360 ordinance, parse with Claude
     (app.services.ordinance_parser), write proposed_verdicts.json. NO DB writes.
  2. Reviewer checks proposed_verdicts.json against the ordinance (Chrome), edits
     the JSON in place with corrections.
  3. --apply <file>: promote the (corrected) verdicts into zone_use_matrix tagged
     with the verbatim municipality, classification_source='human',
     human_reviewed=true. (Apply goes through the prod /zones endpoints so it
     needs no direct DB access; implemented after the JSON shape is reviewed.)

The parser DISCOVERS every district from the ordinance text (ordinance_parse.md
line 9/288), so no per-city known-code list is required — we pass [] and the
LLM enumerates. municipality strings below are the VERBATIM parcels.city values
(TIGER MCD form) the buybox LATERAL join keys on.

Run (dry-run):
  cd backend && .venv/Scripts/python.exe scripts/pattern_bergen_nj_parse.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

BERGEN_JID = "4bf00234-4455-4987-a067-b22ee6b6aa1f"

# Prod API (Railway "ParcelLogic"). Override with PARCELLOGIC_API_BASE for local.
API_BASE = os.environ.get(
    "PARCELLOGIC_API_BASE",
    "https://capable-serenity-production-0d1a.up.railway.app",
).rstrip("/")

# Cities promoted by --apply. Teaneck is intentionally EXCLUDED: its parser-
# inferred codes (B-1/B-2/B-R/L-I) don't match the real parcels.zoning_code
# values (HRO/B3/R50) and only ~42 of ~5K Teaneck parcels carry any code, so
# the verdicts can't bind. Teaneck is deferred to the Tier-2 binding workstream
# (pull complete zoning_code from a spatial source, reconcile codes, re-apply).
APPLY_CITIES = ("Paramus borough", "Elmwood Park borough")

# (verbatim parcels.city municipality, eCode360 ordinance URL from
# backend/data/bergen_zoning_directory.json)
# URLs updated 2026-06-02 to deep use-regulation nodes (the directory's chapter
# roots landed on preamble/attachment nodes that under-retrieved). Paired with
# the 80k->200k truncation-cap bump (ordinance_fetcher + ordinance_parser) so
# large chapters keep their commercial/industrial (B-*/L-I) districts.
#
# A city may carry EITHER `ordinance_url` (single node) OR `ordinance_urls`
# (list — fetched and merged before one parse). Paramus's eCode360 splits each
# district into its own article with no consolidated use schedule, so the
# full-chapter crawl can't reach the use tables; we fetch the commercial-corridor
# articles directly. Residential R-* / industrial articles are deferred to a
# future sprint (they stay covered by absence -> prohibited-by-default).
CITIES = [
    {
        "municipality": "Paramus borough",
        "ordinance_urls": [
            "https://ecode360.com/8546091",  # HCC Zone (general)
            "https://ecode360.com/8546154",  # Article XXII: Highway Corridor Commercial (HCC)
            "https://ecode360.com/8546142",  # HCC-2 Zone
        ],
        "coverage_note": "Commercial corridor only (HCC/HCC-2); R-* & industrial articles deferred.",
    },
    # "DISTRICT LAND USE REGULATIONS" node — the bullseye use-regulations node.
    {"municipality": "Elmwood Park borough", "ordinance_url": "https://ecode360.com/35182106"},
    # Same fat single-chapter root as before; the cap bump is what salvages it.
    {"municipality": "Teaneck township", "ordinance_url": "https://ecode360.com/13628370"},
]

OUT_PATH = Path(__file__).parent / "proposed_verdicts.json"


async def draft_city(city: dict) -> dict:
    """Fetch + LLM-parse one city's ordinance. Returns a review record; never
    raises (errors are captured into the record so one bad city doesn't abort
    the batch)."""
    from app.services.ordinance_fetcher import fetch_from_url
    from app.services.ordinance_parser import parse_ordinance_sections

    muni = city["municipality"]
    # A city carries either a single ordinance_url or a list of ordinance_urls
    # (Paramus: one article per district -> fetch + merge each).
    urls = city.get("ordinance_urls") or [city["ordinance_url"]]
    rec: dict = {"municipality": muni, "ordinance_url": urls if len(urls) > 1 else urls[0]}
    if city.get("coverage_note"):
        rec["coverage_note"] = city["coverage_note"]

    sections = []
    fetch_errors: list[str] = []
    for u in urls:
        try:
            secs = await fetch_from_url(u)
        except Exception as exc:  # noqa: BLE001
            fetch_errors.append(f"{u}: {exc}")
            continue
        sections.extend(secs or [])
    if not sections:
        detail = "; ".join(fetch_errors) if fetch_errors else "0 sections (JS-render / empty)"
        rec.update(error=f"fetch failed: {detail}", zones=[])
        return rec
    if fetch_errors:
        rec["fetch_warnings"] = fetch_errors

    combined = "\n\n".join(
        f"[Section {s.section_id}: {s.heading}]\n{s.text}" for s in sections
    )
    rec["sections_fetched"] = len(sections)
    rec["chars_combined"] = len(combined)

    try:
        # known_zone_codes=[] -> parser enumerates every district from the text.
        output = await parse_ordinance_sections(combined, f"{muni}, NJ", [])
    except Exception as exc:  # noqa: BLE001
        rec.update(error=f"claude parse failed: {exc}", zones=[])
        return rec

    # Dedupe by code, keep highest confidence (mirrors the prod endpoint).
    seen: dict[str, object] = {}
    for z in output.zones:
        if z.code not in seen or z.confidence > seen[z.code].confidence:
            seen[z.code] = z

    rec["zones"] = [
        {
            "zone_code": z.code,
            "zone_name": z.name,
            "self_storage": z.self_storage,
            "mini_warehouse": z.mini_warehouse,
            "light_industrial": z.light_industrial,
            "luxury_garage_condo": z.luxury_garage_condo,
            "confidence": z.confidence,
            "citations": [c.model_dump() for c in (z.citations or [])],
            "notes": z.notes,
        }
        for z in sorted(seen.values(), key=lambda z: z.code)
    ]
    rec["zone_count"] = len(rec["zones"])
    rec["unknown_zones"] = list(output.unknown_zones or [])
    rec["parser_warnings"] = list(output.parser_warnings or [])
    return rec


async def run_dry_run() -> None:
    results = []
    for city in CITIES:
        src = city.get("ordinance_urls") or city.get("ordinance_url")
        print(f"[draft] {city['municipality']} <- {src}", file=sys.stderr)
        rec = await draft_city(city)
        n = rec.get("zone_count", 0)
        if rec.get("error"):
            print(f"  ERROR: {rec['error']}", file=sys.stderr)
        else:
            print(f"  ok: {n} zones, {rec.get('sections_fetched')} sections, "
                  f"{rec.get('chars_combined')} chars", file=sys.stderr)
        results.append(rec)

    out = {
        "jurisdiction_id": BERGEN_JID,
        "jurisdiction_name": "Bergen County, NJ",
        "generated_for_review": True,
        "review_instructions": (
            "verdicts: city -> zone_code -> {4 uses}. Each use cell carries "
            "permission (permitted|conditional|prohibited|unclear), confidence, "
            "cited_subsection, conditions_json, verification_note. Edit permission "
            "values in place against the ordinance, then run --apply on this file. "
            "NOTE: confidence/cited_subsection/verification_note are zone-level "
            "(the parser grounds the whole zone, not each use separately); "
            "conditions_json is null unless a use is conditional with stated terms. "
            "diagnostics holds per-city fetch coverage — check chars_combined / "
            "parser_warnings before trusting a city's verdicts."
        ),
        "verdicts": _to_keyed_verdicts(results),
        "diagnostics": _to_diagnostics(results),
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWROTE {OUT_PATH}", file=sys.stderr)


def _to_keyed_verdicts(results: list[dict]) -> dict:
    """city -> zone_code -> {zone_name, <use>: {permission, confidence,
    cited_subsection, conditions_json, verification_note}} for the 4 matrix
    uses. Maps zone-level confidence/citation/notes onto each use cell (the
    parser grounds per-zone, not per-use)."""
    uses = ("self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo")
    out: dict = {}
    for rec in results:
        muni = rec["municipality"]
        city_block: dict = {}
        for z in rec.get("zones", []):
            cites = z.get("citations") or []
            cited = cites[0].get("section") if cites else None
            note = z.get("notes")
            conf = z.get("confidence")
            zone_block = {"zone_name": z.get("zone_name")}
            for use in uses:
                zone_block[use] = {
                    "permission": z.get(use),
                    "confidence": conf,
                    "cited_subsection": cited,
                    "conditions_json": None,
                    "verification_note": note,
                }
            city_block[z["zone_code"]] = zone_block
        out[muni] = city_block
    return out


def _to_diagnostics(results: list[dict]) -> dict:
    """Per-city fetch/parse coverage so the reviewer can spot under-retrieval
    (low chars_combined, parser warnings) before trusting verdicts."""
    out: dict = {}
    for rec in results:
        out[rec["municipality"]] = {
            "ordinance_url": rec.get("ordinance_url"),
            "coverage_note": rec.get("coverage_note"),
            "sections_fetched": rec.get("sections_fetched"),
            "chars_combined": rec.get("chars_combined"),
            "zone_count": rec.get("zone_count", 0),
            "unknown_zones": rec.get("unknown_zones", []),
            "parser_warnings": rec.get("parser_warnings", []),
            "fetch_warnings": rec.get("fetch_warnings", []),
            "error": rec.get("error"),
        }
    return out


def _payload_for_zone(muni: str, zone_code: str, block: dict) -> dict:
    """Build a ZoneUseMatrixCreate body from one keyed-verdict zone block.

    confidence/citation/note are zone-level (the parser grounds the whole zone,
    not each use), so we read them off the self_storage cell. notes carries the
    cited subsection + the parser's verification rationale for the verifier UI.
    """
    cell = block.get("self_storage", {})
    cited = cell.get("cited_subsection")
    vnote = cell.get("verification_note") or ""
    note = f"[§ {cited}] {vnote}".strip() if cited else vnote
    return {
        "zone_code": zone_code,
        "zone_name": block.get("zone_name"),
        "municipality": muni,
        "self_storage": block["self_storage"]["permission"],
        "mini_warehouse": block["mini_warehouse"]["permission"],
        "light_industrial": block["light_industrial"]["permission"],
        "luxury_garage_condo": block["luxury_garage_condo"]["permission"],
        "classification_source": "human",
        "confidence": cell.get("confidence") or 0.0,
        "notes": note[:2048] or None,
        "human_reviewed": True,
    }


async def run_apply(path: str) -> None:
    """Promote APPLY_CITIES verdicts into prod zone_use_matrix via the HTTP
    /zones endpoints (no direct DB). 201=created; 409=row exists -> PATCH the
    verdicts+notes; anything else is reported and counted as a failure."""
    import httpx

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    verdicts = data.get("verdicts", {})
    base = f"{API_BASE}/api/jurisdictions/{BERGEN_JID}/zones"
    created = updated = skipped = failed = 0

    print(f"[apply] target {base}", file=sys.stderr)
    print(f"[apply] cities {list(APPLY_CITIES)} (Teaneck deferred)\n", file=sys.stderr)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for muni in APPLY_CITIES:
            zones = verdicts.get(muni)
            if not zones:
                print(f"  WARN: {muni} not in file — skipped", file=sys.stderr)
                continue
            for zone_code, block in zones.items():
                payload = _payload_for_zone(muni, zone_code, block)
                try:
                    r = await client.post(base, json=payload)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print(f"  FAIL  {muni} / {zone_code}: {exc}", file=sys.stderr)
                    continue
                if r.status_code == 201:
                    created += 1
                    print(f"  201   {muni} / {zone_code} "
                          f"(ss={payload['self_storage']})", file=sys.stderr)
                elif r.status_code == 409:
                    # Row exists — PATCH verdicts + notes (PATCH can't set
                    # human_reviewed, but the existing row already carries it
                    # if a prior apply created it).
                    purl = (f"{base}/{quote(zone_code, safe='')}"
                            f"?municipality={quote(muni, safe='')}")
                    patch_body = {
                        "self_storage": payload["self_storage"],
                        "mini_warehouse": payload["mini_warehouse"],
                        "light_industrial": payload["light_industrial"],
                        "luxury_garage_condo": payload["luxury_garage_condo"],
                        "notes": payload["notes"],
                    }
                    pr = await client.patch(purl, json=patch_body)
                    if pr.status_code == 200:
                        updated += 1
                        print(f"  409->PATCH 200  {muni} / {zone_code}", file=sys.stderr)
                    else:
                        failed += 1
                        print(f"  409->PATCH {pr.status_code}  {muni} / {zone_code}: "
                              f"{pr.text[:200]}", file=sys.stderr)
                else:
                    failed += 1
                    print(f"  {r.status_code}  {muni} / {zone_code}: "
                          f"{r.text[:200]}", file=sys.stderr)

    print(f"\n[apply] done: created={created} updated={updated} "
          f"skipped={skipped} failed={failed}", file=sys.stderr)
    if failed:
        raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Fetch+parse, write proposed_verdicts.json, NO DB writes.")
    g.add_argument("--apply", metavar="FILE",
                   help="Promote a reviewed proposed_verdicts.json into prod "
                        "zone_use_matrix (Paramus + Elmwood Park; Teaneck deferred).")
    args = ap.parse_args()

    if args.dry_run:
        asyncio.run(run_dry_run())
    else:
        asyncio.run(run_apply(args.apply))


if __name__ == "__main__":
    main()
