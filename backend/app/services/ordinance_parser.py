"""
Ordinance parser — uses Claude Sonnet 4.6 to build the zone→use matrix.

Pipeline:
  1. Build a combined text from all OrdinanceSections.
  2. Call Claude with the system prompt + ordinance text + known zone codes.
  3. Validate the JSON response with Pydantic.
  4. Retry once on JSON/validation failure, appending the error to the prompt.
  5. Apply the luxury_garage_condo inference rule to every zone.
  6. Return a validated ParserOutput.

Snapshot support (for golden-file tests):
  Set ORDINANCE_SNAPSHOT_PATH env var to a file path.
  - If the file exists and RECORD_SNAPSHOT != "1": replay from file (no API call).
  - If RECORD_SNAPSHOT == "1" or file does not exist: call Claude and save result.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import anthropic
from pydantic import ValidationError

from app.config import settings
from app.schemas.zone_use_matrix import ParserOutput, ParserZoneResult

logger = logging.getLogger(__name__)

# ─── Synonym dictionary ───────────────────────────────────────────────────────
# Keep in sync with prompts/ordinance_parse.md

USE_SYNONYMS: dict[str, list[str]] = {
    "self_storage": [
        "self-storage",
        "self storage",
        "mini-storage",
        "mini storage",
        "mini-warehouse",
        "mini warehouse",
        "personal storage",
        "storage facility",
        "storage warehouse",
    ],
    "mini_warehouse": [
        "mini-warehouse",
        "mini warehouse",
        "mini-storage",
        "mini storage",
    ],
    "light_industrial": [
        "light industrial",
        "light manufacturing",
        "limited industrial",
        "research and development",
        "flex industrial",
        "assembly",
        "fabrication (limited)",
    ],
    "luxury_garage_condo": [
        "garage condominium",
        "garage condo",
        "private garage condominium",
        "automotive condominium",
        "rv and boat storage condominium",
        "motorcoach condominium",
        "motor vehicle storage (private, owned)",
        # Fallback signals — ordinances rarely name this use directly
    ],
}


# ─── Public API ──────────────────────────────────────────────────────────────

async def parse_ordinance_sections(
    sections_text: str,
    jurisdiction_name: str,
    known_zone_codes: list[str],
    snapshot_path: Path | None = None,
) -> ParserOutput:
    """
    Send ordinance text to Claude and return a validated ParserOutput.

    Args:
        sections_text:     Combined ordinance text (all sections joined).
        jurisdiction_name: Human-readable name for logging.
        known_zone_codes:  Zone codes found in parcel data (hint to parser).
        snapshot_path:     Optional path for golden-file snapshot recording/replay.

    Returns:
        ParserOutput with zones classified and luxury_garage_condo inferred.
    """
    system_prompt = _load_system_prompt()
    user_message = _build_user_message(sections_text, jurisdiction_name, known_zone_codes)

    # ── Snapshot replay ────────────────────────────────────────────────────
    effective_snapshot = snapshot_path or _env_snapshot_path()
    if effective_snapshot and effective_snapshot.exists() and os.environ.get("RECORD_SNAPSHOT") != "1":
        logger.info("Replaying parser snapshot from %s", effective_snapshot)
        raw_json = json.loads(effective_snapshot.read_text())["raw_response"]
        return _build_output(raw_json)

    # ── Live Claude call ───────────────────────────────────────────────────
    last_error: str | None = None
    for attempt in range(2):
        if attempt > 0 and last_error:
            logger.warning("Retrying Claude parse for %s (attempt 2)", jurisdiction_name)
            user_message = (
                user_message
                + f"\n\n[RETRY REQUIRED: The previous response failed validation with error: "
                f"{last_error}. Return ONLY valid JSON matching the schema exactly.]"
            )
        try:
            raw_json = await asyncio.to_thread(_call_claude, system_prompt, user_message)
            raw_json = _strip_markdown_fences(raw_json)
            output = _build_output(raw_json)

            # ── Save snapshot ──────────────────────────────────────────────
            if effective_snapshot and (
                not effective_snapshot.exists()
                or os.environ.get("RECORD_SNAPSHOT") == "1"
            ):
                effective_snapshot.parent.mkdir(parents=True, exist_ok=True)
                effective_snapshot.write_text(json.dumps({
                    "jurisdiction": jurisdiction_name,
                    "raw_response": raw_json,
                }, indent=2))
                logger.info("Saved parser snapshot to %s", effective_snapshot)

            return output

        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            last_error = str(exc)
            logger.warning("Claude parse attempt %d failed: %s", attempt + 1, exc)

    # ── Both attempts failed — fallback ────────────────────────────────────
    logger.error("Parser failed for %s after 2 attempts: %s", jurisdiction_name, last_error)
    fallback_zones = [
        ParserZoneResult(
            code=code,
            self_storage="unclear",
            mini_warehouse="unclear",
            light_industrial="unclear",
            luxury_garage_condo="unclear",
            confidence=0.0,
            notes=f"Parser failed: {last_error}",
        )
        for code in known_zone_codes
    ]
    return ParserOutput(
        zones=fallback_zones,
        unknown_zones=[],
        parser_warnings=[f"Parser failed after 2 attempts: {last_error}"],
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _load_system_prompt() -> str:
    path = Path(__file__).parent.parent / "prompts" / "ordinance_parse.md"
    return path.read_text(encoding="utf-8")


def _build_user_message(
    sections_text: str,
    jurisdiction_name: str,
    known_zone_codes: list[str],
) -> str:
    codes_str = ", ".join(known_zone_codes) if known_zone_codes else "unknown"
    # Truncate text to avoid excessive token usage
    text = sections_text[:75_000]
    return (
        f"Jurisdiction: {jurisdiction_name}\n"
        f"Known zone codes to classify: {codes_str}\n\n"
        f"ORDINANCE TEXT:\n\n{text}"
    )


def _call_claude(system_prompt: str, user_message: str) -> str:
    """Synchronous Claude call — run via asyncio.to_thread from async context."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` fences if Claude added them despite instructions."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _validate_parser_output(raw_json: str) -> ParserOutput:
    """Parse and validate Claude's JSON response. Raises on failure."""
    data = json.loads(raw_json)
    return ParserOutput.model_validate(data)


def _build_output(raw_json: str) -> ParserOutput:
    """Parse, validate, and apply the luxury_garage_condo inference rule."""
    output = _validate_parser_output(raw_json)
    fixed = [
        ParserZoneResult.model_validate(_apply_luxury_garage_inference(z.model_dump()))
        for z in output.zones
    ]
    return ParserOutput(
        zones=fixed,
        unknown_zones=output.unknown_zones,
        parser_warnings=output.parser_warnings,
    )


def _apply_luxury_garage_inference(zone: dict[str, Any]) -> dict[str, Any]:
    """
    Apply the luxury_garage_condo inference rule when the ordinance is silent.
    Rule (applied in order):
      1. mini_warehouse or self_storage == permitted  → permitted
      2. mini_warehouse or self_storage == conditional → conditional
      3. light_industrial == permitted or conditional  → conditional
      4. none of the above                             → prohibited
    Only overrides when luxury_garage_condo is 'unclear' or None.
    """
    lgc = zone.get("luxury_garage_condo")
    if lgc not in ("unclear", None):
        return zone   # Explicit value from Claude — respect it

    ss = zone.get("self_storage")
    mw = zone.get("mini_warehouse")
    li = zone.get("light_industrial")

    if mw == "permitted" or ss == "permitted":
        zone["luxury_garage_condo"] = "permitted"
    elif mw == "conditional" or ss == "conditional":
        zone["luxury_garage_condo"] = "conditional"
    elif li in ("permitted", "conditional"):
        zone["luxury_garage_condo"] = "conditional"
    else:
        zone["luxury_garage_condo"] = "prohibited"

    return zone


def _env_snapshot_path() -> Path | None:
    """Read snapshot path from ORDINANCE_SNAPSHOT_PATH env var."""
    raw = os.environ.get("ORDINANCE_SNAPSHOT_PATH")
    return Path(raw) if raw else None
