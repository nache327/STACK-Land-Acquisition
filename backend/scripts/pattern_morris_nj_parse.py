"""LLM-draft per-town zone verdicts for Morris County, NJ — Batch 2 (wealth pockets).

Targets (all ~100% bound via NJTPA layer 4, so verdicts bind immediately):
  Mendham borough/township, Chester borough/township, Harding township,
  Madison borough, Florham Park borough.

Needle-candidate districts (the rare commercial/industrial zones a storage deal
could hide in, from _morris_codes.py):
  Chester borough   I (4) / M-H (1) / LBT / B-1..B-3 / O-P,O-T
  Madison borough   G-I (7) / G-II (5) / CBD-1,2 / CC / PCD-O / OR
  Florham Park      M-2 (1) / P&B-1,2 (163) / C-1..C-4 / POD-S
  Mendham borough   HB (51) / LB / EB
  Mendham township  CR-1, CR-2 (265) / B
  Chester township  LB (65) / B / PO/R
  Harding township  B-1 (12) / B-2 (42) / OB

Same workflow as pattern_bergen_nj_parse.py: --dry-run fetches + Claude-parses
each town's eCode360 node(s), writes proposed_verdicts_morris.json (NO DB
writes); reviewer eyeballs; verdicts then applied via a gated apply script
(reconciled to the actual parcels.zoning_code per municipality).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

MORRIS_JID = "746b7604-f362-470f-aa42-70dc8973b4ee"

# Discovered eCode360 nodes. A town carries ordinance_urls (list, merged before
# one parse). Deep use-regulation nodes preferred (chapter roots under-retrieve).
# Re-run subset: only the two towns that needed deeper sourcing.
#   Mendham borough HB = ordinance "Historic Business" (NJTPA mislabels it
#     "Highway Business"); add Historic Business (6683037) + East Business (6683095).
#   Chester township: prior root (12402684) was an empty adoption header; use the
#     real district nodes (permitted uses 12403551, LB 12403569, PO/R 12403583).
CITIES = [
    {"municipality": "Mendham borough", "ordinance_urls": [
        "https://ecode360.com/6683037",   # Art VI Historic Business (HB) Zone  <- the real HB
        "https://ecode360.com/6683095",   # East Business (EB) Zone
        "https://ecode360.com/6683081",   # Limited Business (LB) Zone
        "https://ecode360.com/6682660",   # Zoning Districts
    ]},
    {"municipality": "Chester township", "ordinance_urls": [
        "https://ecode360.com/12403551",  # Permitted uses (use schedule)
        "https://ecode360.com/12403569",  # LB Limited Business Zone
        "https://ecode360.com/12403583",  # PO/R Professional Office/Residential
    ]},
]

OUT_PATH = Path(__file__).parent / "proposed_verdicts_morris2.json"


async def draft_city(city: dict) -> dict:
    from app.services.ordinance_fetcher import fetch_from_url
    from app.services.ordinance_parser import parse_ordinance_sections

    muni = city["municipality"]
    urls = city.get("ordinance_urls") or [city["ordinance_url"]]
    rec: dict = {"municipality": muni, "ordinance_url": urls if len(urls) > 1 else urls[0]}

    sections, fetch_errors = [], []
    for u in urls:
        try:
            secs = await fetch_from_url(u)
        except Exception as exc:  # noqa: BLE001
            fetch_errors.append(f"{u}: {exc}")
            continue
        sections.extend(secs or [])
    if not sections:
        detail = "; ".join(fetch_errors) if fetch_errors else "0 sections"
        rec.update(error=f"fetch failed: {detail}", zones=[])
        return rec
    if fetch_errors:
        rec["fetch_warnings"] = fetch_errors

    combined = "\n\n".join(f"[Section {s.section_id}: {s.heading}]\n{s.text}" for s in sections)
    rec["sections_fetched"] = len(sections)
    rec["chars_combined"] = len(combined)

    try:
        output = await parse_ordinance_sections(combined, f"{muni}, NJ", [])
    except Exception as exc:  # noqa: BLE001
        rec.update(error=f"claude parse failed: {exc}", zones=[])
        return rec

    seen: dict[str, object] = {}
    for z in output.zones:
        if z.code not in seen or z.confidence > seen[z.code].confidence:
            seen[z.code] = z
    rec["zones"] = [
        {"zone_code": z.code, "zone_name": z.name, "self_storage": z.self_storage,
         "mini_warehouse": z.mini_warehouse, "light_industrial": z.light_industrial,
         "luxury_garage_condo": z.luxury_garage_condo, "confidence": z.confidence,
         "citations": [c.model_dump() for c in (z.citations or [])], "notes": z.notes}
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
        if rec.get("error"):
            print(f"  ERROR: {rec['error']}", file=sys.stderr)
        else:
            print(f"  ok: {rec.get('zone_count')} zones, {rec.get('sections_fetched')} "
                  f"sections, {rec.get('chars_combined')} chars", file=sys.stderr)
        results.append(rec)
    OUT_PATH.write_text(json.dumps({
        "jurisdiction_id": MORRIS_JID, "jurisdiction_name": "Morris County, NJ",
        "generated_for_review": True, "results": results,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nWROTE {OUT_PATH}", file=sys.stderr)
    # inline reviewer table — non-prohibited zones first
    print("\n=== REVIEWER TABLE (non-prohibited zones) ===", file=sys.stderr)
    for rec in results:
        for z in rec.get("zones", []):
            uses = (z["self_storage"], z["mini_warehouse"], z["light_industrial"])
            if any(u != "prohibited" for u in uses):
                cite = (z.get("citations") or [{}])[0].get("section", "")
                print(f"  {rec['municipality']:20} {z['zone_code']:10} "
                      f"ss={z['self_storage']:11} li={z['light_industrial']:11} "
                      f"conf={z['confidence']}  [{cite}]", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.parse_args()
    asyncio.run(run_dry_run())


if __name__ == "__main__":
    main()
