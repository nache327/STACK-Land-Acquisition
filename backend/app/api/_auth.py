"""Shared-secret auth for operator/CLI-only admin routes (Tier-0 security MVP).

Gated routes require an `X-Admin-Secret` header matching `settings.admin_api_secret`
(env `ADMIN_API_SECRET`). This protects the high-severity operator surface (arbitrary
migrations, DDL, jurisdiction-delete, bulk-zoning writes, scoring, digest, backfills,
zoning-upload) that the public frontend never calls, and which the CLI scripts drive.

NOT applied to the in-app admin console's routes (op5 adjudications, listings upload,
force-rerun, ring-metrics/bulk, buybox-filter CRUD, zone-verifier PATCH) — a browser SPA
can't hold a shared secret, so those need real per-user auth (a later phase).

Fail-closed: if `admin_api_secret` is unset, gated routes return 503 rather than being
left open. Set ADMIN_API_SECRET in the API env (Railway) and in scripts before deploy.
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_secret(
    x_admin_secret: str | None = Header(default=None, alias="X-Admin-Secret"),
) -> None:
    expected = settings.admin_api_secret
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin auth not configured (ADMIN_API_SECRET unset).",
        )
    if not x_admin_secret or not hmac.compare_digest(x_admin_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")
