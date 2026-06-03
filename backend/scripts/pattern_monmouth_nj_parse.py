"""LLM-draft per-city zone verdicts for Monmouth County, NJ — wealth-pocket sprint.

Twin of scripts/pattern_somerset_nj_parse.py (same fetch -> parse -> keyed JSON
-> review -> apply -> anti-junk-gate flow); only the county config below differs.

Target (parse + apply):
  - Marlboro township (14,326 parcels, 100% zoning_code coded, district extent
    overlap 1.0 — verdicts bind immediately). This is the ONLY bind-ready town
    in Monmouth: the binding diagnostic (2026-06-03) found Monmouth 5.7% coded
    overall, with ALL coded parcels in Marlboro. Every other Monmouth town is 0%
    coded (no district polygons ingested), so parsing them would not bind — that
    needs district-polygon ingestion first (the real NJ bottleneck), tracked
    separately. Hunterdon + Morris are 0% coded county-wide; deferred likewise.

Run (dry-run):
  cd backend && .venv/Scripts/python.exe scripts/pattern_monmouth_nj_parse.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

MONMOUTH_JID = "703d95b4-3229-42f8-8bb1-460d46b3ceb2"

# Prod API (Railway "ParcelLogic"). Override with PARCELLOGIC_API_BASE for local.
API_BASE = os.environ.get(
    "PARCELLOGIC_API_BASE",
    "https://capable-serenity-production-0d1a.up.railway.app",
).rstrip("/")

# (verbatim parcels.city municipality, eCode360 deep use-regulation node).
# A city may carry `ordinance_url` (single) OR `ordinance_urls` (list, merged).
CITIES = [
    # Article III: Zoning Standards and Regulations (Ch. 220 Land Use and
    # Development) — the per-district use lists. Parent "Zoning: Standards and
    # Regulations" is 12878051 if Art III under-retrieves.
    {"municipality": "Marlboro township", "ordinance_url": "https://ecode360.com/12875623"},
]

# Cities promoted by --apply. Marlboro is 100% coded so every verdict binds.
APPLY_CITIES = ("Marlboro township",)

OUT_PATH = Path(__file__).parent / "proposed_verdicts_monmouth.json"


async def draft_city(city: dict) -> dict:
    """Fetch + LLM-parse one city's ordinance. Returns a review record; never
    raises (errors are captured into the record so one bad city doesn't abort
    the batch)."""
    from app.services.ordinance_fetcher import fetch_from_url
    from app.services.ordinance_parser import parse_ordinance_sections

    muni = city["municipality"]
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


async def run_dry_run(only: set[str] | None = None) -> None:
    cities = CITIES
    if only:
        cities = [c for c in CITIES if c["municipality"] in only]
        missing = only - {c["municipality"] for c in cities}
        if missing:
            raise SystemExit(f"--only names not in CITIES: {sorted(missing)}")

    results = []
    for city in cities:
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

    # Subset re-run: merge re-parsed cities into the existing file instead of
    # clobbering the cities we didn't re-run (e.g. the slow healthy ones).
    if only and OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        existing.setdefault("verdicts", {}).update(_to_keyed_verdicts(results))
        existing.setdefault("diagnostics", {}).update(_to_diagnostics(results))
        OUT_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        print(f"\nMERGED {sorted(only)} into {OUT_PATH}", file=sys.stderr)
        return

    out = {
        "jurisdiction_id": MONMOUTH_JID,
        "jurisdiction_name": "Monmouth County, NJ",
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
    """Build a ZoneUseMatrixCreate body from one keyed-verdict zone block."""
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
    base = f"{API_BASE}/api/jurisdictions/{MONMOUTH_JID}/zones"
    created = updated = skipped = held = failed = 0

    print(f"[apply] target {base}", file=sys.stderr)
    print(f"[apply] cities {list(APPLY_CITIES)}\n", file=sys.stderr)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Anti-junk gate (the Teaneck lesson): only write codes that exist in
        # the jurisdiction's actual parcels.zoning_code set, else the row can
        # never bind. zone-summary is jurisdiction-wide (no city filter) so this
        # is a coarse presence check — a matched code at worst no-ops for a city
        # that lacks it, but an UNmatched code is guaranteed dead. Held codes
        # (invented names, format variants like RR3 vs RR-3) are reported.
        summ = await client.get(f"{base.rsplit('/zones',1)[0]}/parcels/zone-summary")
        real_codes = set(summ.json().keys()) if summ.status_code == 200 else set()
        if not real_codes:
            raise SystemExit("could not fetch parcel zone-summary for the gate; aborting")
        print(f"[apply] gate: {len(real_codes)} real parcel codes\n", file=sys.stderr)

        for muni in APPLY_CITIES:
            zones = verdicts.get(muni)
            if not zones:
                print(f"  WARN: {muni} not in file — skipped", file=sys.stderr)
                continue
            for zone_code, block in zones.items():
                if zone_code not in real_codes:
                    held += 1
                    print(f"  HELD  {muni} / {zone_code} (not in parcels)", file=sys.stderr)
                    continue
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
                    # Query-param PATCH route: handles zone codes with '/'
                    # (B/R etc.) that 404 on the path route. base ends in
                    # '/zones' -> '/zone'.
                    purl = (f"{base[:-1]}?zone_code={quote(zone_code, safe='')}"
                            f"&municipality={quote(muni, safe='')}")
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
          f"held={held} skipped={skipped} failed={failed}", file=sys.stderr)
    if failed:
        raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Fetch+parse, write proposed_verdicts_monmouth.json, NO DB writes.")
    g.add_argument("--apply", metavar="FILE",
                   help="Promote a reviewed proposed_verdicts_monmouth.json into prod "
                        "zone_use_matrix (Marlboro township).")
    ap.add_argument("--only", default=None,
                    help="Comma-separated municipalities to re-run (merged into the "
                         "existing JSON). E.g. --only 'Franklin township,Warren township'")
    args = ap.parse_args()

    if args.dry_run:
        only = {s.strip() for s in args.only.split(",")} if args.only else None
        asyncio.run(run_dry_run(only))
    else:
        asyncio.run(run_apply(args.apply))


if __name__ == "__main__":
    main()
