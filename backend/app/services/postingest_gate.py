"""Post-ingest / post-apply health gate (hardening plan item 2.5).

The anti-poison backstop that must pass before a jurisdiction's verdicts are
trusted — especially now that parallel sessions ground different munis into the
same county. It complements `municipality_health` (operational trustworthiness);
this module asserts the *data-integrity* invariants that catch silent-wrong:

  1. URL-SHAPED CODES — a zoning_code that is a URL or absurdly long is a bind
     failure (catch #34 family: eCode360 URLs bound as zone codes). HARD FAIL.
  2. CONSTANT-DOMINATION — a single code covering >90% of coded parcels across
     many distinct geometries is the `Type="District"` / catch #33 signature of
     a mis-bound field. HARD FAIL.
  3. UNCLEAR-MASQUERADING-AS-GROUNDED — a matrix row whose classification_source
     is a grounded authority (human/llm/…) yet every use column is 'unclear'
     claims grounding while saying nothing; it inflates coverage and can present
     as a verified verdict. HARD FAIL.
  4. MATRIX COVERAGE — % of coded parcels whose zoning_code has any matrix row,
     and % bound (parcels with a zoning_code). Soft floors (warn), since a fresh
     ingest legitimately starts low.

Fails loud: `run_postingest_gate` returns a report with `passed: bool`; the CLI
exits non-zero on any HARD failure so a bad parallel apply can't silently ship.
Pure helpers (`is_url_shaped`, `dominant_code`) are unit-tested without a DB.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

# zone_use_matrix.zone_code is String(50); a real district code is short.
_MAX_CODE_LEN = 20
_URL_RE = re.compile(r"^\s*https?://", re.I)

# Sources that claim a grounded verdict (mirror buybox GROUNDED_SOURCES).
_GROUNDED_SOURCES = ("human", "llm", "llm_rule", "op5_factory")

# Soft coverage floors (warn, not fail — a fresh ingest starts low).
_MIN_BOUND_PCT = 0.50
_MIN_MATRIX_COVERAGE_PCT = 0.20
# Constant-domination trip: one code over this share across at least this many
# distinct codes present (a legit single-district town won't have many codes).
_DOMINATION_PCT = 0.90
_DOMINATION_MIN_DISTINCT = 5

# Named-garage-use markers (lowercased). Presence in a lgc row's basis text means
# the permitted/conditional luxury_garage_condo rests on a NAMED ordinance use
# (e.g. Marlborough "hobby vehicle storage") — legitimate, exempt from the
# sibling-consistency check (catch #58). Absence + prohibited storage siblings is
# the Billerica-shaped inference leak.
_NAMED_GARAGE_MARKERS = (
    "hobby vehicle", "garage condo", "garage condominium", "motor vehicle storage",
    "rv and boat", "rv/boat", "motorcoach", "automotive condominium",
)


def sibling_consistency_violation(ss, mw, lgc, basis_text) -> bool:
    """Catch #58, automated: a luxury_garage_condo verdict of permitted/conditional
    while BOTH storage siblings (self_storage, mini_warehouse) are prohibited is a
    consistency leak — UNLESS lgc rests on a named garage use. Garage-condo is
    leased dead storage, the same use-family as self-storage; if the ordinance
    prohibits ss/mw (a definitive negative, e.g. closed-list), an inferred lgc that
    stays permitted/conditional contradicts it. Named-use lgc (Marlborough) is
    exempt. `basis_text` = the row's notes + citation quotes, lowercased here."""
    if (lgc or "").lower() not in ("permitted", "conditional"):
        return False
    if (ss or "").lower() != "prohibited" or (mw or "").lower() != "prohibited":
        return False
    text = (basis_text or "").lower()
    return not any(m in text for m in _NAMED_GARAGE_MARKERS)


def is_url_shaped(code: str | None) -> bool:
    """True if a zoning_code is a URL or absurdly long — a bind failure."""
    if not code:
        return False
    return bool(_URL_RE.search(code)) or len(code.strip()) > _MAX_CODE_LEN


def dominant_code(counts: dict[str, int]) -> tuple[str, float] | None:
    """Given {code: parcel_count}, return (code, share) if one code dominates
    >_DOMINATION_PCT across >=_DOMINATION_MIN_DISTINCT distinct codes, else None.
    A single-district town (few distinct codes) never trips this."""
    total = sum(counts.values())
    if total == 0 or len(counts) < _DOMINATION_MIN_DISTINCT:
        return None
    code, n = max(counts.items(), key=lambda kv: kv[1])
    share = n / total
    return (code, share) if share > _DOMINATION_PCT else None


@dataclass
class GateReport:
    jurisdiction_id: str
    passed: bool = True
    hard_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def fail(self, msg: str) -> None:
        self.hard_failures.append(msg)
        self.passed = False

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


async def run_postingest_gate(conn, jurisdiction_id: uuid.UUID | str) -> GateReport:
    """Run the anti-poison assertions against a jurisdiction using a raw asyncpg
    connection. Returns a GateReport; `passed=False` on any HARD failure."""
    jid = str(jurisdiction_id)
    rep = GateReport(jurisdiction_id=jid)

    total = await conn.fetchval(
        "SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid", jid)
    coded = await conn.fetchval(
        "SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL", jid)
    rep.stats["parcels_total"] = total
    rep.stats["parcels_coded"] = coded
    if not total:
        rep.warn("no parcels for jurisdiction")
        return rep

    bound_pct = coded / total
    rep.stats["bound_pct"] = round(bound_pct, 4)
    if bound_pct < _MIN_BOUND_PCT:
        rep.warn(f"only {bound_pct:.1%} of parcels have a zoning_code (< {_MIN_BOUND_PCT:.0%})")

    # Per-code parcel counts (coded parcels only)
    rows = await conn.fetch(
        """SELECT zoning_code AS code, count(*) AS n FROM parcels
           WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
           GROUP BY 1""", jid)
    counts = {r["code"]: r["n"] for r in rows}
    rep.stats["distinct_codes"] = len(counts)

    # 1. URL-shaped codes — HARD
    url_codes = [c for c in counts if is_url_shaped(c)]
    if url_codes:
        rep.fail(f"URL-shaped / over-length zoning_code(s): {url_codes[:5]}"
                 f"{' …' if len(url_codes) > 5 else ''} ({len(url_codes)} distinct)")

    # 2. Constant-domination — HARD
    dom = dominant_code(counts)
    if dom:
        rep.fail(f"single code '{dom[0]}' covers {dom[1]:.1%} of {coded:,} coded parcels "
                 f"across {len(counts)} codes — likely a mis-bound field")

    # 3. Unclear-masquerading-as-grounded — HARD (matrix rows)
    masq = await conn.fetch(
        """SELECT municipality, zone_code FROM zone_use_matrix
           WHERE jurisdiction_id=$1::uuid AND deleted_at IS NULL
             AND classification_source::text = ANY($2::text[])
             AND self_storage='unclear' AND mini_warehouse='unclear'
             AND light_industrial='unclear' AND luxury_garage_condo='unclear'""",
        jid, list(_GROUNDED_SOURCES))
    if masq:
        sample = [f"{r['municipality']}/{r['zone_code']}" for r in masq[:5]]
        rep.fail(f"{len(masq)} grounded-source matrix row(s) with ALL uses 'unclear' "
                 f"(claims grounding, says nothing): {sample}")

    # 3b. Sibling-consistency (catch #58) — HARD. A lgc verdict of permitted/
    # conditional while BOTH storage siblings are prohibited, with no named-garage
    # basis, is the Billerica-shaped inference leak. Basis text = notes + citation
    # quotes.
    lgc_rows = await conn.fetch(
        """SELECT municipality, zone_code, self_storage::text ss, mini_warehouse::text mw,
                  luxury_garage_condo::text lgc, coalesce(notes,'') AS notes,
                  coalesce(citations::text,'') AS cites
             FROM zone_use_matrix
            WHERE jurisdiction_id=$1::uuid AND deleted_at IS NULL
              AND luxury_garage_condo IN ('permitted','conditional')""", jid)
    leaks = [
        f"{r['municipality']}/{r['zone_code']}"
        for r in lgc_rows
        if sibling_consistency_violation(r["ss"], r["mw"], r["lgc"], r["notes"] + " " + r["cites"])
    ]
    if leaks:
        rep.fail(f"catch-#58 sibling leak — lgc permitted/conditional (inference basis) while "
                 f"ss+mw prohibited: {leaks[:5]}{' …' if len(leaks) > 5 else ''} ({len(leaks)} rows)")

    # 4. Matrix coverage — SOFT
    covered = await conn.fetchval(
        """SELECT count(*) FROM parcels p WHERE p.jurisdiction_id=$1::uuid
             AND p.zoning_code IS NOT NULL
             AND EXISTS (SELECT 1 FROM zone_use_matrix m
                         WHERE m.jurisdiction_id=p.jurisdiction_id
                           AND m.zone_code=p.zoning_code
                           AND (m.municipality=p.city OR m.municipality IS NULL)
                           AND m.deleted_at IS NULL)""", jid)
    cov_pct = covered / coded if coded else 0.0
    rep.stats["matrix_coverage_pct"] = round(cov_pct, 4)
    if cov_pct < _MIN_MATRIX_COVERAGE_PCT:
        rep.warn(f"only {cov_pct:.1%} of coded parcels have a matrix row (< {_MIN_MATRIX_COVERAGE_PCT:.0%})")

    return rep
