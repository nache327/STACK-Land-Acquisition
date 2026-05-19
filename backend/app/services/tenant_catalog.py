"""tenant_catalog — vendor-tenant cataloging for ArcGIS Online zoning publishers.

A small number of consulting vendors publish municipal zoning across many NJ
towns on shared ArcGIS Online tenants. Once an operator verifies one source on
a tenant, every other zoning-named service on that tenant becomes a high-
priority candidate for sibling municipalities.

The catalog lives at `backend/data/zoning_source_tenants.json`. Per-row shape:

    {
      "tenants": {
        "<host>/<orgid>": {
          "vendor": str,
          "discovered_via": "verified_source" | "hub_search" | "manual",
          "verified_munis": [{"muni": str, "state": str, "service_name": str}],
          "candidate_munis": [{"muni": str, "state": str, "service_name": str}],
          "non_zoning_munis": [str],
          "notes": str,
          "last_enumerated_at": "YYYY-MM-DD"
        }
      },
      "denylist": {"prefixes": [str, ...]}
    }

This module is read-mostly. Writes happen on operator verify-actions through
`add_verified_muni()`. Tenant enumeration / probing is in
`enumerate_tenant_services()` — pure HTTP, no DB.

Design rules:
  - Catalog is a JSON file, not a DB table. v1 simplicity; migration trivial later.
  - tenant_prefix() is canonical — derived deterministically from a service URL.
  - is_known_tenant() is O(1); calls in scoring hot path must stay cheap.
  - Auto-grow on _review verify is best-effort; failures must not break the
    verify action.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


logger = logging.getLogger(__name__)


_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "zoning_source_tenants.json"

# Catalog write-lock — async since the only writer is the API _review handler.
_WRITE_LOCK = asyncio.Lock()

# Match ArcGIS Online service URL: scheme://services{n}.arcgis.com/{orgid}/arcgis/rest/services/...
_ARCGIS_PATH_RE = re.compile(r"^/?([A-Za-z0-9]{8,})/arcgis/rest/services(/|$)", re.I)


def tenant_prefix(url: str | None) -> str | None:
    """Canonical tenant prefix `<host>/<orgid>` for an ArcGIS Online service URL.

    Returns None for non-ArcGIS URLs or unparseable inputs. Pure function — no
    network, no I/O.

    Examples:
      >>> tenant_prefix("https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Paramus_Zoning/FeatureServer/0")
      'services6.arcgis.com/UcuMPLF9IlsigGHI'
      >>> tenant_prefix("https://services1.arcgis.com/ze0XBzU1FXj94DJq/ArcGIS/rest/services/X/FeatureServer")
      'services1.arcgis.com/ze0XBzU1FXj94DJq'
    """
    if not url:
        return None
    try:
        p = urlparse(url)
    except Exception:
        return None
    host = (p.hostname or "").lower()
    if not host.endswith("arcgis.com"):
        return None
    m = _ARCGIS_PATH_RE.match(p.path or "")
    if not m:
        return None
    orgid = m.group(1)
    return f"{host}/{orgid}"


def _load_catalog() -> dict:
    """Read the JSON catalog from disk. Returns the parsed dict or an empty
    skeleton if the file is missing or corrupt."""
    if not _CATALOG_PATH.exists():
        return {"_meta": {}, "tenants": {}, "denylist": {"prefixes": []}}
    try:
        return json.loads(_CATALOG_PATH.read_text())
    except Exception as exc:
        logger.warning("zoning_source_tenants.json parse failed: %r", exc)
        return {"_meta": {}, "tenants": {}, "denylist": {"prefixes": []}}


def _save_catalog(data: dict) -> None:
    """Persist the catalog to disk. Atomic write via temp + rename."""
    tmp = _CATALOG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(_CATALOG_PATH)


def is_known_tenant(url: str | None) -> bool:
    """True iff the URL's tenant has at least one verified muni in the catalog.

    O(1) lookup; safe to call from scoring hot path.
    """
    tp = tenant_prefix(url)
    if not tp:
        return False
    cat = _load_catalog()
    entry = cat.get("tenants", {}).get(tp)
    if entry is None:
        return False
    return bool(entry.get("verified_munis"))


def is_denylisted_tenant(url: str | None) -> bool:
    """True iff the URL's tenant prefix is in the operator deny-list.

    Used by scoring to penalize known generic-FP tenants regardless of
    individual URL state.
    """
    tp = tenant_prefix(url)
    if not tp:
        return False
    cat = _load_catalog()
    return tp in set((cat.get("denylist") or {}).get("prefixes") or [])


def known_tenants() -> list[str]:
    """All tenant prefixes that have at least one verified muni — used by
    discovery sweep to drive tenant-directory enumeration."""
    cat = _load_catalog()
    out = []
    for tp, entry in (cat.get("tenants") or {}).items():
        if entry.get("verified_munis"):
            out.append(tp)
    return out


async def add_verified_muni(
    url: str | None,
    municipality_name: str | None,
    state: str | None,
    service_name: str | None,
    vendor: str | None = None,
) -> bool:
    """Auto-grow hook — called by jurisdictions._review on a verify action.

    Idempotent: re-verifying the same (tenant, muni, service_name) is a no-op.
    Errors are logged + swallowed so they cannot fail the verify flow.

    Returns True if the catalog was updated, False if it was a no-op or failed.
    """
    tp = tenant_prefix(url)
    if not tp or not municipality_name:
        return False
    try:
        async with _WRITE_LOCK:
            cat = _load_catalog()
            tenants = cat.setdefault("tenants", {})
            entry = tenants.setdefault(tp, {
                "vendor": vendor or "Unknown",
                "discovered_via": "verified_source",
                "verified_munis": [],
                "candidate_munis": [],
                "non_zoning_munis": [],
                "notes": "",
                "last_enumerated_at": None,
            })
            key = (municipality_name, state, service_name)
            already = any(
                (v.get("muni"), v.get("state"), v.get("service_name")) == key
                for v in entry.get("verified_munis") or []
            )
            if already:
                return False
            entry.setdefault("verified_munis", []).append({
                "muni": municipality_name,
                "state": state,
                "service_name": service_name,
            })
            # Promote from candidate_munis to verified_munis if present
            entry["candidate_munis"] = [
                c for c in entry.get("candidate_munis") or []
                if (c.get("muni"), c.get("state"), c.get("service_name")) != key
            ]
            cat.setdefault("_meta", {})["last_updated"] = date.today().isoformat()
            _save_catalog(cat)
            logger.info(
                "tenant_catalog: verified %s/%s on tenant %s",
                state or "?", municipality_name, tp,
            )
            return True
    except Exception as exc:
        logger.warning("tenant_catalog.add_verified_muni failed: %r", exc)
        return False


async def enumerate_tenant_services(
    tenant: str,
    client: httpx.AsyncClient | None = None,
    timeout: float = 15.0,
) -> list[dict]:
    """Fetch the ArcGIS REST directory for a tenant and return its service list.

    Each result is `{"name": str, "type": "FeatureServer"|"MapServer", "url": str}`.

    Returns [] on any failure. No caching here — caller decides whether to
    persist last_enumerated_at.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        url = f"https://{tenant}/arcgis/rest/services?f=json"
        resp = await client.get(url, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return []
        data = resp.json() or {}
        svcs = data.get("services") or []
        return [
            {
                "name": s.get("name") or "",
                "type": s.get("type") or "",
                "url": s.get("url") or f"https://{tenant}/arcgis/rest/services/{s.get('name')}/{s.get('type')}",
            }
            for s in svcs
            if s.get("name") and s.get("type") in ("FeatureServer", "MapServer")
        ]
    except Exception as exc:
        logger.warning("enumerate_tenant_services failed for %s: %r", tenant, exc)
        return []
    finally:
        if own_client:
            await client.aclose()


# Service-name matcher used by tenant_directory_sweep — handles underscore
# tokenization (ArcGIS service names commonly use _ as separator). Avoids the
# Python `\b` pitfall where `_` is a word char.

def _normalize_service_name(name: str) -> str:
    """Lowercase + collapse non-alphanumeric runs to single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (name or "").lower())).strip()


def is_zoning_service_name(name: str) -> bool:
    """True if the service name contains a zoning keyword. Catches underscore-
    separated `Paramus_Zoning`, mixed `WestwoodZoning2019`, etc."""
    n = _normalize_service_name(name)
    return any(k in n for k in ("zoning", "landuse", "land use"))


def matches_municipality(name: str, muni: str) -> bool:
    """True if the (normalized) service name plausibly refers to this muni.

    Rules (strict — designed to avoid Iteration-1 substring FPs):
      1. Full muni name as concat (>=7 chars) appears in name's concat form.
      2. All tokens of a multi-word muni appear as whole words.
      3. A single-word muni's only token (>=7 chars) appears as a whole word.

    >>> matches_municipality("Westwood_Zoning_2019", "Westwood")
    True
    >>> matches_municipality("Franklin_County_Zoning_Map_WFL1", "Franklin Lakes")
    False
    >>> matches_municipality("Paramus_Zoning", "Paramus")
    True
    """
    n_normspaces = _normalize_service_name(name)
    n_concat = n_normspaces.replace(" ", "")
    ml = (muni or "").lower()
    tokens = ml.split()
    muni_concat = re.sub(r"[^a-z0-9]", "", ml)
    if len(muni_concat) >= 7 and muni_concat in n_concat:
        return True
    if len(tokens) >= 2:
        return all(
            re.search(rf"(^|\s){re.escape(t)}(\s|$)", n_normspaces) for t in tokens
        )
    if len(tokens) == 1 and len(tokens[0]) >= 7:
        return bool(re.search(rf"(^|\s){re.escape(tokens[0])}(\s|$)", n_normspaces))
    return False


async def tenant_directory_sweep(
    municipality_names: list[str],
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """Walk every known tenant's service directory and surface any zoning-named
    service that matches one of the given municipality names.

    Returns a list of `{tenant, muni, service_name, service_type, url}` dicts.
    Caller persists them into zoning_sources via the existing _probe_layer +
    _persist_candidates pipeline (no DB access in this module).
    """
    candidates: list[dict] = []
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
    try:
        for tenant in known_tenants():
            svcs = await enumerate_tenant_services(tenant, client=client)
            for s in svcs:
                if not is_zoning_service_name(s["name"]):
                    continue
                muni = next((m for m in municipality_names if matches_municipality(s["name"], m)), None)
                if not muni:
                    continue
                candidates.append({
                    "tenant": tenant,
                    "muni": muni,
                    "service_name": s["name"],
                    "service_type": s["type"],
                    "url": s["url"],
                })
    finally:
        if own_client:
            await client.aclose()
    return candidates
