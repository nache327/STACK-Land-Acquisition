"""ArcGIS source lookup for Op-5 munis (CP-Pre Finding 5).

Many NJ munis are already published as ArcGIS FeatureServer layers via two
known sources:

* ``backend/data/zoning_source_tenants.json`` — vendor-tenant catalog. Two
  shape classes consumed here:
  - ``tenants[<host>].verified_munis`` — operator-confirmed muni→service
    mappings (e.g. Paramus on
    ``services6.arcgis.com/UcuMPLF9IlsigGHI``).
  - ``tenants[<host>].candidate_munis`` — same shape, lower confidence
    (e.g. Westwood on
    ``services6.arcgis.com/UcuMPLF9IlsigGHI/.../Westwood_Zoning_2019``).
  - ``tenants[<host>].non_zoning_munis`` — exclusion list (services that
    look zoning-named but operator confirmed aren't real zoning sources).

* ``backend/data/bergen_zoning_directory.json`` — per-muni records with an
  ``in_njsea_zoning`` boolean. NJSEA Meadowlands towns are aggregated into
  one statewide layer at
  ``services1.arcgis.com/ze0XBzU1FXj94DJq/.../20200609_Zoning/FeatureServer/0``
  and partitioned by ``MUN_CODE`` (4-digit; Bergen prefix ``02``).

This module is pure logic — no network calls. The classifier and per-muni
runner call :func:`lookup_arcgis_source`; if it returns a non-None
:class:`ArcgisSource`, the caller probes the FeatureServer and (on success)
skips the PDF/vision pipeline entirely.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

LOGGER = logging.getLogger("op5_lib.arcgis_lookup")

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "backend" / "data"

TENANTS_PATH = DATA_DIR / "zoning_source_tenants.json"
BERGEN_DIRECTORY_PATH = DATA_DIR / "bergen_zoning_directory.json"

# NJSEA statewide layer — fixed per BERGEN_INGEST_RUNBOOK.md.
NJSEA_FEATURE_SERVER_URL = (
    "https://services1.arcgis.com/ze0XBzU1FXj94DJq/arcgis/rest/services/"
    "20200609_Zoning/FeatureServer/0"
)
# Field used for partitioning the NJSEA layer per Bergen muni.
NJSEA_PARTITION_FIELD = "MUN_CODE"
# County FIPS prefixes the NJSEA layer carries.  Bergen = "02".
COUNTY_FIPS_BY_NAME = {
    "bergen": "02",
    "hudson": "09",
    "essex": "07",
    "morris": "14",
    "passaic": "16",
    "union": "20",
}


# ── DCA suffix handling ────────────────────────────────────────────────────


_DCA_SUFFIXES = (
    " borough",
    " township",
    " town",
    " city",
    " village",
)


def _strip_suffix(name: str) -> str:
    """Lowercase + strip the common NJ DCA suffix.

    "Westwood Borough" -> "westwood".  The tenant catalog stores bare
    names ("Westwood", "Paramus") so this normalization is the join key.
    """
    lower = (name or "").strip().lower()
    for suf in _DCA_SUFFIXES:
        if lower.endswith(suf):
            return lower[: -len(suf)].strip()
    return lower


# ── data shapes ────────────────────────────────────────────────────────────


@dataclass
class ArcgisSource:
    """An ArcGIS FeatureServer source for a muni's zoning layer."""

    feature_server_url: str
    where_clause: Optional[str]      # e.g. "MUN_CODE LIKE '0205%'" for NJSEA
    source_label: str                # human-readable label
    confidence: str                  # "verified" | "candidate" | "njsea"
    tenant_host: str                 # "services6.arcgis.com/UcuMPLF9IlsigGHI" or NJSEA host


# ── tenant catalog helpers ─────────────────────────────────────────────────


def _load_tenants(path: Path = TENANTS_PATH) -> dict:
    if not path.exists():
        LOGGER.warning("zoning_source_tenants.json not found at %s", path)
        return {"tenants": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        LOGGER.warning("malformed tenants catalog at %s: %s", path, exc)
        return {"tenants": {}}


def _load_bergen_directory(path: Path = BERGEN_DIRECTORY_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        LOGGER.warning("malformed bergen directory at %s: %s", path, exc)
        return []


def is_arcgis_candidate_excluded(muni_name: str, tenant: dict) -> bool:
    """True if the muni is in ``tenant.non_zoning_munis``.

    Operator-confirmed "this tenant has a service named like the muni but
    it isn't a real zoning layer" exclusions take precedence over
    candidate matches.
    """
    target = _strip_suffix(muni_name)
    for n in tenant.get("non_zoning_munis", []) or []:
        if _strip_suffix(str(n)) == target:
            return True
    return False


def _match_tenant_muni_list(
    muni_name: str, state: str, entries: Iterable[dict]
) -> Optional[dict]:
    """Return the first entry matching (muni, state) by stripped name."""
    target = _strip_suffix(muni_name)
    target_state = (state or "").strip().upper()
    for entry in entries:
        entry_state = str(entry.get("state", "")).strip().upper()
        if entry_state != target_state:
            continue
        if _strip_suffix(str(entry.get("muni", ""))) == target:
            return entry
    return None


def _tenant_service_url(host: str, service_name: str) -> str:
    """Build the canonical FeatureServer/0 URL for a tenant + service."""
    host = host.strip().rstrip("/")
    return f"https://{host}/arcgis/rest/services/{service_name}/FeatureServer/0"


# ── NJSEA helpers ──────────────────────────────────────────────────────────


def _bergen_muni_code(muni_name: str) -> Optional[str]:
    """Look up the 4-digit Bergen muni_code from the directory."""
    target = _strip_suffix(muni_name)
    for row in _load_bergen_directory():
        if _strip_suffix(row.get("muni_name", "")) == target:
            code = (row.get("muni_code") or "").strip()
            return code or None
    return None


def _is_in_njsea(muni_name: str) -> bool:
    target = _strip_suffix(muni_name)
    for row in _load_bergen_directory():
        if _strip_suffix(row.get("muni_name", "")) == target:
            return bool(row.get("in_njsea_zoning"))
    return False


def _njsea_where_clause(muni_code: str) -> str:
    """``MUN_CODE LIKE '<4digit>%'`` per the runbook."""
    return f"{NJSEA_PARTITION_FIELD} LIKE '{muni_code}%'"


# ── public lookup ──────────────────────────────────────────────────────────


def lookup_arcgis_source(
    muni_name: str,
    state: str,
    *,
    tenants_path: Path = TENANTS_PATH,
    bergen_directory_path: Path = BERGEN_DIRECTORY_PATH,
) -> Optional[ArcgisSource]:
    """Return the ArcGIS source for a muni, or None if not ArcGIS-served.

    Priority:

    1. ``tenants[*].verified_munis`` match → ``confidence='verified'``.
    2. ``tenants[*].candidate_munis`` match (excluding
       ``tenant.non_zoning_munis``) → ``confidence='candidate'``.
    3. NJSEA via ``bergen_zoning_directory.json[muni].in_njsea_zoning=True``
       → use the ``20200609_Zoning/FeatureServer/0`` layer with WHERE
       clause ``MUN_CODE LIKE '<county_fips><muni_fips>%'`` (lookup
       muni_code from the directory).
    4. Else None.
    """
    if not muni_name:
        return None

    catalog = _load_tenants(tenants_path)
    tenants = catalog.get("tenants", {})

    # Pass 1: verified.
    for host, tenant in tenants.items():
        match = _match_tenant_muni_list(
            muni_name, state, tenant.get("verified_munis", []) or [],
        )
        if match:
            service_name = match.get("service_name")
            if not service_name:
                continue
            url = _tenant_service_url(host, service_name)
            label = f"{match.get('muni')} {service_name} (verified tenant {host})"
            return ArcgisSource(
                feature_server_url=url,
                where_clause=None,
                source_label=label,
                confidence="verified",
                tenant_host=host,
            )

    # Pass 2: candidate (after exclusion check).
    for host, tenant in tenants.items():
        if is_arcgis_candidate_excluded(muni_name, tenant):
            continue
        match = _match_tenant_muni_list(
            muni_name, state, tenant.get("candidate_munis", []) or [],
        )
        if match:
            service_name = match.get("service_name")
            if not service_name:
                continue
            url = _tenant_service_url(host, service_name)
            label = f"{match.get('muni')} {service_name} (candidate tenant {host})"
            return ArcgisSource(
                feature_server_url=url,
                where_clause=None,
                source_label=label,
                confidence="candidate",
                tenant_host=host,
            )

    # Pass 3: NJSEA (Bergen-only directory today; structurally identical
    # for any other county-directory that ships ``in_njsea_zoning``).
    if (state or "").strip().upper() == "NJ" and _is_in_njsea(muni_name):
        muni_code = _bergen_muni_code(muni_name)
        if muni_code:
            return ArcgisSource(
                feature_server_url=NJSEA_FEATURE_SERVER_URL,
                where_clause=_njsea_where_clause(muni_code),
                source_label=f"NJSEA 20200609_Zoning (muni_code={muni_code})",
                confidence="njsea",
                tenant_host="services1.arcgis.com/ze0XBzU1FXj94DJq",
            )

    return None


# ── live FeatureServer probe ───────────────────────────────────────────────


def _build_probe_url(feature_server_url: str, where_clause: Optional[str]) -> str:
    """Compose a ``returnCountOnly=true`` URL for the layer."""
    from urllib.parse import quote_plus

    clause = (where_clause or "1=1").strip() or "1=1"
    return (
        f"{feature_server_url.rstrip('/')}/query"
        f"?where={quote_plus(clause)}"
        f"&returnCountOnly=true&f=json"
    )


def probe_feature_server(
    feature_server_url: str,
    where_clause: Optional[str] = None,
    *,
    timeout_s: float = 30.0,
) -> bool:
    """Probe a FeatureServer layer for life + non-zero feature count.

    Performs ``GET <url>/query?where=<clause>&returnCountOnly=true&f=json``.
    Success criteria: HTTP 200 + JSON with ``count > 0``.

    Returns ``False`` on any error (timeout, non-200, malformed JSON, count
    <= 0).  Never raises.
    """
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("httpx missing — cannot probe %s: %s", feature_server_url, exc)
        return False
    probe_url = _build_probe_url(feature_server_url, where_clause)
    try:
        resp = httpx.get(
            probe_url,
            timeout=timeout_s,
            headers={"User-Agent": "ParcelLogic/1.0 Op5ArcgisProbe"},
            follow_redirects=True,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("FeatureServer probe failed for %s: %s", feature_server_url, exc)
        return False
    if resp.status_code >= 400:
        LOGGER.debug(
            "FeatureServer probe %s -> HTTP %d", feature_server_url, resp.status_code,
        )
        return False
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug(
            "FeatureServer probe %s returned non-JSON: %s", feature_server_url, exc,
        )
        return False
    if not isinstance(data, dict):
        return False
    count = data.get("count")
    try:
        return int(count) > 0
    except (TypeError, ValueError):
        return False
