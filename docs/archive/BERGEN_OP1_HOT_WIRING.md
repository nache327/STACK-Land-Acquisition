# Op-1 Hot-File Wiring Spec

**Date**: 2026-05-15
**Status**: **NOT applied** — `jurisdictions.py` is currently being edited by another in-flight session (rescoring endpoints). This spec is the precise diff for the next Slot-1 cycle to apply once the in-flight PR lands.
**Cold-backend modules are already in place**: `backend/app/services/tenant_catalog.py` + `backend/data/zoning_source_tenants.json` + `backend/tests/test_tenant_catalog.py` (14/14 tests passing as of 2026-05-15).

The full Op-1 design is in `BERGEN_EXECUTION_ROADMAP.md`. This file is the operational hand-off: a Slot-1 session can copy-paste the diffs below.

---

## Diff 1 — `backend/app/services/zoning_discovery.py`

Add the `verified_tenant_match` and `denylisted_tenant` score components inside `_score_candidate` and an import at the top.

### Imports (top of file, after `from app.models.jurisdiction import Jurisdiction`)

```python
from app.services import tenant_catalog
```

### Inside `_score_candidate` (insert before the `return total, components` line at ~line 486)

```python
    # Component I — verified-tenant bonus (Op-1)
    # Auto-elevates services on tenants where the operator has already
    # verified at least one source. Catches sibling-muni discovery
    # (e.g. Westwood_Zoning_2019 on the Paramus vendor tenant).
    if tenant_catalog.is_known_tenant(url):
        components.append(ScoreComponent(
            "verified_tenant_match", 15,
            "url is on an ArcGIS tenant where another source is operator-verified",
        ))

    # Component J — denylisted-tenant penalty (Op-1)
    # Encodes operator's accumulated rejection of generic-FP tenants
    # (e.g. services3.arcgis.com/m3XdyJh55Jrxxk0l — 66 prior rejections).
    if tenant_catalog.is_denylisted_tenant(url):
        components.append(ScoreComponent(
            "denylisted_tenant", -40,
            "tenant is on the operator-curated deny-list of generic-FP publishers",
        ))
```

**Why both components**: the deny-list is the operator's hard signal that the
TENANT is over-publishing generic-name FPs; `verified_tenant_match` is the
operator's hard signal that the TENANT is a legitimate vendor. The Op-1 audit
already populated the catalog with both for Bergen.

Lines added: ~20. Reversible by deleting the two blocks.

---

## Diff 2 — `backend/app/api/jurisdictions.py`

Two changes:
1. New endpoint `POST /api/jurisdictions/{id}/_discover-tenant-services`.
2. Auto-grow hook in the existing `_review` verify path.

### New endpoint (add near the other discovery endpoints — e.g., after `_discover-municipal-zoning`)

```python
@router.post(
    "/{jurisdiction_id}/_discover-tenant-services",
    summary="Enumerate every known vendor tenant's service directory and surface zoning-named services matching the jurisdiction's municipalities.",
)
async def discover_tenant_services(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from app.services import tenant_catalog
    from app.services.nj_municipal_discovery import _load_municipalities
    from app.services.zoning_discovery import (
        _fetch_rejected_endpoints, _persist_candidates, _probe_layer, _name_tokens,
        ZoningCandidate, _TOP_N,
    )
    import httpx, asyncio

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="jurisdiction not found")

    munis = _load_municipalities(j.state or "", j.county or "")
    if not munis:
        return JSONResponse({"jurisdiction_id": str(j.id), "candidates": [], "note": "no municipality list for this jurisdiction"})

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        # 1) Walk known tenants → enumerate directories → match zoning-named services to munis.
        raw_candidates = await tenant_catalog.tenant_directory_sweep(munis, client=client)
        if not raw_candidates:
            return JSONResponse({"jurisdiction_id": str(j.id), "candidates": []})
        # 2) Reuse the existing _probe_layer + scoring path so every candidate
        #    lands in zoning_sources with the same shape as Hub-discovered rows.
        denylist = await _fetch_rejected_endpoints(db)
        persisted: list[dict] = []
        for c in raw_candidates:
            tokens = _name_tokens(c["muni"], j.county)
            # Build a synthetic hub_item to feed _probe_layer.
            hub_item = {"attributes": {
                "name": c["service_name"], "url": c["url"].rstrip("/"),
                "layerId": 0,
            }}
            cand: ZoningCandidate | None = await _probe_layer(
                client, hub_item, None, tokens,
                jurisdiction=j, denylist=denylist,
            )
            if cand is None:
                continue
            await _persist_candidates(db, j, [cand], municipality_name=c["muni"])
            persisted.append({
                "muni": c["muni"], "url": cand.url,
                "title": cand.title, "confidence": cand.confidence,
                "tenant": c["tenant"],
            })
    return JSONResponse({
        "jurisdiction_id": str(j.id),
        "jurisdiction_name": j.name,
        "candidates": persisted,
        "candidate_count": len(persisted),
    })
```

### Auto-grow hook in `_review` (inside the existing handler that processes `verify` actions)

Locate the spot where a single source is updated to `validation_status='verified'`. After the commit, add:

```python
    # Auto-grow tenant catalog when operator confirms a verify (Op-1).
    if action == "verify" and src is not None and src.zoning_endpoint:
        from app.services import tenant_catalog
        await tenant_catalog.add_verified_muni(
            url=src.zoning_endpoint,
            municipality_name=src.municipality_name,
            state=src.state,
            service_name=(src.title or src.zoning_endpoint.rsplit("/", 2)[-2]),
        )
```

The `add_verified_muni` call swallows all exceptions internally, so any
failure cannot break the verify flow.

Lines added: ~60. Reversible by deleting the endpoint + hook.

---

## Pre-merge checklist

- [ ] The in-flight `_rescore-stale-sources` / `_rescore-rollback` PR has merged
- [ ] `pytest backend/tests/test_tenant_catalog.py` passes (already does — 14/14 as of 2026-05-15)
- [ ] `backend/app/services/tenant_catalog.py` and `backend/data/zoning_source_tenants.json` are on `origin/main`
- [ ] Add a new test `backend/tests/test_zoning_discovery_tenant_components.py` covering the two new score components (mirroring existing scoring tests)

## Post-merge verification

After deploy:

1. `curl https://capable-serenity-production-0d1a.up.railway.app/api/admin/coverage` — baseline `parcel_with_zoning_code_count` for Bergen.
2. `curl -X POST https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/4bf00234-4455-4987-a067-b22ee6b6aa1f/_discover-tenant-services` — expect ≥4 candidates persisted (Paramus_Zoning_Rev2020, Paramus_Zoning_Rev2023, Westwood_Zoning_2019, plus any new ones as the catalog grows).
3. `curl 'https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/4bf00234-4455-4987-a067-b22ee6b6aa1f/_sources?municipality=Westwood&status=pending'` — expect at least one row with `confidence_score ≥ 85` and a `verified_tenant_match` in `confidence_breakdown`.

## What this does not include

- Any change to `pipeline.py`, `ingestion.py`, `zoning_system.py`, or `spatial_backfill.py`.
- Any alembic migration.
- Any frontend change.
- The Op-1 catalog file is read-only from the perspective of `pipeline.py` — only the API `_review` handler writes to it, and only via `tenant_catalog.add_verified_muni`.
