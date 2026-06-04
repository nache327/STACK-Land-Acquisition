"""LLM-draft per-town zone verdicts — Batch 3: Hunterdon + Monmouth coastal.

Multi-jurisdiction (each city carries its own jurisdiction_id). All bound ~100%
via NJTPA. Prime needles (from NJTPA zone-label disambiguation):
  Middletown twp  M-1 Industrial (20) / BP Business Park (21) / MC Marine
                  Commercial (145)  <- the real targets
  Sea Bright      B-2/B-3 Business (314) / BR Business Residential (59)
  Spring Lake     GC General Commercial (22)
  Spring Lake Hts B-1/B-2 Business / GC
  (Tewksbury PM = "Piedmont District" conservation, NOT manufacturing — false
   alarm; Deal C = Civic; Allenhurst small commercial — sourced separately)

--dry-run only (no DB writes); writes proposed_verdicts_batch3_ad.json + inline
reviewer table. Apply via a gated script reconciled to parcels.zoning_code.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

HUNTERDON = "e8612f49-218b-48cc-9eb0-a1dd90cf583d"
MONMOUTH = "703d95b4-3229-42f8-8bb1-460d46b3ceb2"

CITIES = [
    {"municipality": "Allenhurst borough", "jid": MONMOUTH, "ordinance_urls": [
        "https://ecode360.com/34621706",  # Chapter 26 Development Regulations (C-1/C-2/B-2)
    ]},
    {"municipality": "Deal borough", "jid": MONMOUTH, "ordinance_urls": [
        "https://ecode360.com/36242592",  # Article X Zoning Regulations (Commercial §30-87.2)
    ]},
]

OUT_PATH = Path(__file__).parent / "proposed_verdicts_batch3_ad.json"


async def draft_city(city: dict) -> dict:
    from app.services.ordinance_fetcher import fetch_from_url
    from app.services.ordinance_parser import parse_ordinance_sections

    muni = city["municipality"]
    urls = city.get("ordinance_urls") or [city["ordinance_url"]]
    rec: dict = {"municipality": muni, "jid": city["jid"],
                 "ordinance_url": urls if len(urls) > 1 else urls[0]}
    sections, fetch_errors = [], []
    for u in urls:
        try:
            sections.extend((await fetch_from_url(u)) or [])
        except Exception as exc:  # noqa: BLE001
            fetch_errors.append(f"{u}: {exc}")
    if not sections:
        rec.update(error=f"fetch failed: {'; '.join(fetch_errors) or '0 sections'}", zones=[])
        return rec
    if fetch_errors:
        rec["fetch_warnings"] = fetch_errors
    combined = "\n\n".join(f"[{s.section_id}: {s.heading}]\n{s.text}" for s in sections)
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
        for z in sorted(seen.values(), key=lambda z: z.code)]
    rec["zone_count"] = len(rec["zones"])
    rec["parser_warnings"] = list(output.parser_warnings or [])
    return rec


async def run_dry_run() -> None:
    results = []
    for city in CITIES:
        print(f"[draft] {city['municipality']} <- {city.get('ordinance_urls')}", file=sys.stderr)
        rec = await draft_city(city)
        if rec.get("error"):
            print(f"  ERROR: {rec['error']}", file=sys.stderr)
        else:
            print(f"  ok: {rec.get('zone_count')} zones, {rec.get('chars_combined')} chars", file=sys.stderr)
        results.append(rec)
    OUT_PATH.write_text(json.dumps({"generated_for_review": True, "results": results},
                                   indent=2, default=str), encoding="utf-8")
    print(f"\nWROTE {OUT_PATH}", file=sys.stderr)
    print("\n=== REVIEWER TABLE (non-prohibited) ===", file=sys.stderr)
    for rec in results:
        for z in rec.get("zones", []):
            if any(z[u] != "prohibited" for u in ("self_storage", "mini_warehouse", "light_industrial")):
                cite = (z.get("citations") or [{}])[0].get("section", "")
                print(f"  {rec['municipality']:26} {z['zone_code']:10} "
                      f"ss={z['self_storage']:11} li={z['light_industrial']:11} "
                      f"conf={z['confidence']} [{cite}]", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.parse_args()
    asyncio.run(run_dry_run())


if __name__ == "__main__":
    main()
