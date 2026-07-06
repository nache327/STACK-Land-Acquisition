"""Admin auth header for scripts that call gated prod API routes.

Gated operator routes (see app/api/_auth.py) require the `X-Admin-Secret` header.
Any script that POSTs to a gated route (e.g. `_score-jurisdiction`,
`_precompute-ring-metrics-worker`, `_match-listings-worker`, `_upload-matrix-rows`,
`_backfill-*`, `_upload-zoning`, `_run-digest`, `/_admin/optimize-parcels`) must send it.

    import httpx
    from scripts._api import admin_headers
    httpx.post(url, json=payload, headers=admin_headers())

Reads ADMIN_API_SECRET from the environment (same value as the API's env). Raises a
clear error if unset, so a re-run fails loudly rather than getting an opaque 401/503.
"""
from __future__ import annotations

import os


def admin_headers() -> dict[str, str]:
    secret = os.environ.get("ADMIN_API_SECRET", "")
    if not secret:
        raise RuntimeError(
            "ADMIN_API_SECRET not set — required to call gated admin API routes. "
            "Export it (same value as the API env) before running this script."
        )
    return {"X-Admin-Secret": secret}
