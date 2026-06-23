"""Retrieve representative ordinance excerpts for verdict-truth review.

This is a small harness around ``app.services.ordinance_fetcher.fetch_from_url``.
It exists so operators can prove whether a municipal-code host is retrievable
without hand-copying browser text into a matrix sprint.

Usage:
    cd backend
    python -m scripts.retrieve_ordinance_excerpts
    python -m scripts.retrieve_ordinance_excerpts --url <url> --section 20.10.440
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from app.services.ordinance_fetcher import OrdinanceSection, fetch_from_url


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = ROOT / "docs" / "AUDIT_NOTES" / "ordinance_extraction_excerpts"


@dataclass(frozen=True)
class Target:
    slug: str
    label: str
    url: str
    section: str
    keywords: tuple[str, ...]


DEFAULT_TARGETS: tuple[Target, ...] = (
    Target(
        slug="bellevue_luc_20_10_440",
        label="Bellevue LUC 20.10.440",
        url="https://bellevue.municipal.codes/LUC/20.10.440",
        section="20.10.440",
        keywords=("land use charts", "uses in land use districts", "manufacturing"),
    ),
    Target(
        slug="bainbridge_bimc_18_06_040",
        label="Bainbridge BIMC 18.06.040",
        url=(
            "https://www.codepublishing.com/WA/BainbridgeIsland/html/"
            "BainbridgeIsland18/BainbridgeIsland1806.html"
        ),
        section="18.06.040",
        keywords=("high school road", "district", "permitted"),
    ),
    Target(
        slug="edina_municode_36_640",
        label="Edina Municode Sec. 36-640",
        url=(
            "https://library.municode.com/mn/edina/codes/code_of_ordinances"
            "?nodeId=SPBLADERE_CH36ZO_ARTVIIIDIDIRE_DIV9PLINDIPI_S36-640PRUS"
        ),
        section="36-640",
        keywords=("planned industrial district", "mini-storage", "principal uses"),
    ),
)


def _section_matches(section: OrdinanceSection, target: Target) -> bool:
    haystack = f"{section.section_id}\n{section.heading}\n{section.text}".lower()
    if target.section.lower() in haystack:
        return True
    return any(keyword.lower() in haystack for keyword in target.keywords)


def _best_excerpt(sections: list[OrdinanceSection], target: Target, max_chars: int) -> str:
    target_section = target.section.lower()
    exact_candidates = [
        section for section in sections
        if section.section_id.lower() == target_section
        or section.text.lower().lstrip().startswith(target_section)
    ]
    if exact_candidates:
        candidates = sorted(exact_candidates, key=lambda section: len(section.text), reverse=True)
    else:
        candidates = [section for section in sections if _section_matches(section, target)]
    if not candidates:
        candidates = sections[:1]

    chosen = candidates[0]
    text = chosen.text.strip()

    # If the chosen section is a whole rendered document, trim around the most
    # useful keyword rather than returning the first page of navigation chrome.
    lower = text.lower()
    pivot = -1
    for needle in (target.section, *target.keywords):
        idx = lower.find(needle.lower())
        if idx >= 0:
            pivot = idx
            break
    if pivot > 0 and len(text) > max_chars:
        start = max(0, pivot - 800)
        text = text[start:start + max_chars]
        if start:
            text = "[...]\n" + text
    else:
        text = text[:max_chars]

    return "\n".join((
        f"# {target.label}",
        "",
        f"Source: {target.url}",
        f"Matched section: {chosen.section_id} — {chosen.heading}",
        f"District codes detected: {', '.join(chosen.district_codes[:30]) or 'none'}",
        "",
        _clean_excerpt_text(text),
        "",
    ))


def _clean_excerpt_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    lines = []
    for line in text.splitlines():
        line = line.rstrip()
        if line:
            lines.append(line)
        elif lines and lines[-1]:
            lines.append("")
    return "\n".join(lines)


async def _retrieve_target(target: Target, out_dir: Path, max_chars: int) -> tuple[Target, bool, str]:
    try:
        sections = await fetch_from_url(target.url)
        excerpt = _best_excerpt(sections, target, max_chars)
        out_path = out_dir / f"{target.slug}.md"
        out_path.write_text(excerpt, encoding="utf-8")
        return target, True, f"{out_path.relative_to(ROOT)} ({len(sections)} sections)"
    except Exception as exc:  # noqa: BLE001
        return target, False, str(exc)


async def _run(targets: tuple[Target, ...], out_dir: Path, max_chars: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for target in targets:
        target, ok, detail = await _retrieve_target(target, out_dir, max_chars)
        status = "PASS" if ok else "HALT"
        if not ok:
            failures += 1
        print(f"{status} {target.label}: {detail}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="single ordinance URL to retrieve")
    parser.add_argument("--section", default="document", help="target section for --url")
    parser.add_argument("--label", default="Custom ordinance excerpt")
    parser.add_argument("--slug", default="custom_ordinance_excerpt")
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-chars", type=int, default=7_500)
    args = parser.parse_args(argv)

    if args.url:
        targets = (Target(
            slug=args.slug,
            label=args.label,
            url=args.url,
            section=args.section,
            keywords=tuple(args.keyword),
        ),)
    else:
        targets = DEFAULT_TARGETS

    return asyncio.run(_run(targets, args.out_dir, args.max_chars))


if __name__ == "__main__":
    sys.exit(main())
