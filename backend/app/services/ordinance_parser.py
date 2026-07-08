"""
Ordinance parser — uses Claude Opus 4.7 to build the zone→use matrix.

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
from app.services.zone_classifier import classify_by_zone_character

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

# Input window sent to Claude; the prohibited-by-silence guard keys off this
# exact boundary, so both must share one constant.
MAX_INPUT_CHARS = 200_000


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
        return _build_output(raw_json, known_zone_codes, sections_text)

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
            output = _build_output(raw_json, known_zone_codes, sections_text)

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

    # ── Both attempts failed — use zone_classifier instead of all-unclear ──
    logger.error("Parser failed for %s after 2 attempts: %s", jurisdiction_name, last_error)
    fallback_zones = []
    for code in known_zone_codes:
        rule = classify_by_zone_character(code)
        d = {
            "code": code,
            "self_storage": rule.self_storage,
            "mini_warehouse": rule.mini_warehouse,
            "light_industrial": rule.light_industrial,
            "luxury_garage_condo": rule.luxury_garage_condo,
            "confidence": rule.confidence,
            "notes": f"[rule-fallback: LLM parse failed after 2 attempts] {rule.notes or ''}",
        }
        d = _apply_luxury_garage_inference(d)
        fallback_zones.append(ParserZoneResult.model_validate(d))
    return ParserOutput(
        zones=fallback_zones,
        unknown_zones=[],
        parser_warnings=[f"Parser failed after 2 attempts: {last_error}. Used rule-based classifier for all zones."],
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
    # Flatten composite codes like "A5; CC; RM2" → individual base codes
    base_codes: set[str] = set()
    for raw in known_zone_codes:
        for part in re.split(r"[;,]", raw):
            code = part.strip()
            if code:
                base_codes.add(code)
    codes_str = ", ".join(sorted(base_codes)) if base_codes else "unknown"
    # Truncate text to avoid excessive token usage. 200k chars (~50k tokens) is
    # well within context and stops large chapters (residential first, then
    # commercial/industrial) from losing their B-*/L-I districts to truncation.
    text = sections_text[:MAX_INPUT_CHARS]
    return (
        f"Jurisdiction: {jurisdiction_name}\n"
        f"Known zone codes to classify: {codes_str}\n\n"
        f"ORDINANCE TEXT:\n\n{text}"
    )


def _call_claude(system_prompt: str, user_message: str) -> str:
    """Synchronous Claude call — run via asyncio.to_thread from async context."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=16000,
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


def _normalize_zone_code(code: str) -> str:
    return re.sub(r"[\s\-_.]", "", code).upper()


def _apply_output_guards(
    output: ParserOutput,
    known_zone_codes: list[str],
    sections_text: str,
) -> ParserOutput:
    """Post-parse guards — the LLM's output is treated as untrusted until proven
    against the parcel data and the source text (2.3):

    1. Zone-code membership: a returned code that isn't a known parcel code is
       routed to unknown_zones instead of becoming a matrix row (hallucinated /
       ordinance-only districts never bind).
    2. Citation quotes must appear verbatim (whitespace-insensitive) in the
       source text; failed quotes are dropped, and a zone left with no
       surviving citation is capped at confidence 0.5 (ungrounded).
    3. Prohibited-by-silence requires the silence to be in text we actually
       sent: when input was truncated at MAX_INPUT_CHARS and a zone's code
       never appears in the sent window, its "prohibited" slots downgrade to
       "unclear" (the zone's rows may simply have been cut off).
    """
    warnings = list(output.parser_warnings)
    unknown = list(output.unknown_zones)

    known: set[str] = set()
    for raw in known_zone_codes:
        for part in re.split(r"[;,]", raw):
            if part.strip():
                known.add(_normalize_zone_code(part))

    truncated = len(sections_text) > MAX_INPUT_CHARS
    seen_text = sections_text[:MAX_INPUT_CHARS]
    seen_norm = " ".join(seen_text.split()).lower()

    # Catch #56 pre-check: text-layer extraction is blind to revision marks.
    # A token that concatenates two valid grid symbols (NSZ, SZY, ...) on a
    # use-table row means tracked changes until visually disproven — warn so
    # a human eyeballs the cell before any verdict rests on it.
    _SYMBOLS = ("SZ", "SP", "SA", "Y", "N")
    _tok_re = re.compile(r"\b(?:%s){2,3}\b" % "|".join(_SYMBOLS))
    for line in seen_text.splitlines():
        singles = sum(1 for t in line.split() if t in _SYMBOLS)
        if singles < 3:
            continue  # not a use-grid row
        for tok in _tok_re.findall(line):
            if tok in _SYMBOLS:
                continue
            warnings.append(
                f"guard[compound-token]: '{tok}' on a use-grid row concatenates two "
                f"valid symbols — possible tracked-change/strikethrough cell (catch #56); "
                f"visual check required: {' '.join(line.split())[:100]}"
            )

    kept: list[ParserZoneResult] = []
    for zone in output.zones:
        if known and _normalize_zone_code(zone.code) not in known:
            unknown.append(zone.code)
            warnings.append(
                f"guard[membership]: '{zone.code}' is not a known parcel zone code — "
                "routed to unknown_zones, no matrix row written"
            )
            continue

        d = zone.model_dump()

        surviving = []
        for c in zone.citations:
            quote_norm = " ".join((c.quote or "").split()).lower()
            if quote_norm and quote_norm in seen_norm:
                surviving.append(c.model_dump())
            else:
                warnings.append(
                    f"guard[quote]: citation for '{zone.code}' ({c.section}) is not a "
                    "verbatim substring of the source text — citation dropped"
                )
        if len(surviving) != len(zone.citations):
            d["citations"] = surviving
            if not surviving and zone.citations:
                d["confidence"] = min(d["confidence"], 0.5)
                d["notes"] = f"[guard: all citations failed verbatim check] {d.get('notes') or ''}"

        if truncated and not re.search(
            rf"(?<![A-Za-z0-9]){re.escape(zone.code)}(?![A-Za-z0-9])", seen_text, re.I
        ):
            downgraded = False
            for use_key in ("self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo"):
                if d.get(use_key) == "prohibited":
                    d[use_key] = "unclear"
                    downgraded = True
            if downgraded:
                d["notes"] = f"[guard: input truncated and '{zone.code}' unseen — prohibited-by-silence downgraded to unclear] {d.get('notes') or ''}"
                warnings.append(
                    f"guard[silence]: input truncated at {MAX_INPUT_CHARS} chars and "
                    f"'{zone.code}' never appears in the sent window — its prohibited "
                    "verdicts downgraded to unclear"
                )

        kept.append(ParserZoneResult.model_validate(d))

    return ParserOutput(zones=kept, unknown_zones=unknown, parser_warnings=warnings)


def _validate_parser_output(raw_json: str) -> ParserOutput:
    """Parse and validate Claude's JSON response. Raises on failure."""
    data = json.loads(raw_json)
    return ParserOutput.model_validate(data)


_CONFIDENCE_FLOOR = 0.70  # Below this, fill "unclear" slots with zone_classifier


def _apply_zone_classifier_floor(zones: list[ParserZoneResult]) -> list[ParserZoneResult]:
    """
    For any zone where confidence < _CONFIDENCE_FLOOR OR any use column = "unclear",
    apply classify_by_zone_character() to fill the unclear slots.

    Rules:
    - Never overrides a concrete LLM value (permitted / conditional / prohibited).
    - Only fills slots that are "unclear".
    - Re-applies luxury_garage_condo inference after filling.
    - Tags notes with "[llm+rule: ...]" when the rule classifier was used.
    """
    result: list[ParserZoneResult] = []
    for zone in zones:
        has_unclear = any(
            getattr(zone, use) == "unclear"
            for use in ("self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo")
        )
        is_low_conf = (zone.confidence or 0.0) < _CONFIDENCE_FLOOR

        if not has_unclear and not is_low_conf:
            result.append(zone)
            continue

        rule = classify_by_zone_character(zone.code)
        rule_used = False
        d = zone.model_dump()

        for use_key in ("self_storage", "mini_warehouse", "light_industrial"):
            if d.get(use_key) == "unclear":
                d[use_key] = getattr(rule, use_key)
                rule_used = True

        # Re-apply luxury_garage_condo inference with resolved values
        d = _apply_luxury_garage_inference(d)

        if rule_used:
            d["notes"] = f"[llm+rule: zone_classifier filled unclear slots] {d.get('notes') or ''}"

        result.append(ParserZoneResult.model_validate(d))
    return result


def _build_output(
    raw_json: str,
    known_zone_codes: list[str] | None = None,
    sections_text: str | None = None,
) -> ParserOutput:
    """Parse, validate, guard, apply inference rule, and apply zone_classifier floor."""
    output = _validate_parser_output(raw_json)
    if known_zone_codes is not None and sections_text is not None:
        output = _apply_output_guards(output, known_zone_codes, sections_text)
    fixed = [
        ParserZoneResult.model_validate(_apply_luxury_garage_inference(z.model_dump()))
        for z in output.zones
    ]
    fixed = _apply_zone_classifier_floor(fixed)
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
