# Ordinance Extraction Adapter HALT/PASS

Date: 2026-06-22

## Verdict

**PASS for verdict-truth excerpt retrieval.** The backend now has a source-aware fallback path for municipal-code hosts that block direct fetches or require browser rendering:

1. Code Publishing: direct static HTML first, Jina Reader fallback.
2. municipal.codes, Municode, American Legal, enCodePlus: existing Playwright path first, Jina Reader fallback.
3. eCode360: existing generic/SPA path first, Jina Reader fallback.

This is **not** an anti-bot defeat and does not require a Municode subscription. When direct/browser retrieval fails, the adapter asks Jina Reader for public rendered text and preserves the canonical source URL in the excerpt output.

## Implementation

- Backend adapter: `backend/app/services/ordinance_fetcher.py`
  - Added host classification for `codepublishing.com` and `encodeplus.com`.
  - Added `_fetch_via_jina_reader()` fallback for supported code platforms.
  - Rejects challenge shells and "content not found" responses instead of silently returning unusable text.
  - Uses reader-specific headers for Jina; browser-style source headers caused Jina 403s in live probes.
- Operator harness: `backend/scripts/retrieve_ordinance_excerpts.py`
  - Runs representative source URLs through the production fetcher.
  - Writes source-attributed markdown excerpts to `docs/AUDIT_NOTES/ordinance_extraction_excerpts/`.
  - Supports custom URL/section retrieval for the queued verdict-truth cohort.

## Three-Source Proof

| Target | Host pattern | Direct result | Adapter path | Result |
|---|---:|---:|---:|---:|
| Bellevue LUC 20.10.440 | municipal.codes / Cloudflare | 403 challenge | Jina rendered text | PASS |
| Bainbridge BIMC 18.06.040 | Code Publishing | intermittent 403 via httpx | Jina rendered text fallback | PASS |
| Edina Sec. 36-640 | Municode | API 401 / SPA shell | Jina rendered official `nodeId` URL | PASS |

Generated excerpts:

- `docs/AUDIT_NOTES/ordinance_extraction_excerpts/bellevue_luc_20_10_440.md`
- `docs/AUDIT_NOTES/ordinance_extraction_excerpts/bainbridge_bimc_18_06_040.md`
- `docs/AUDIT_NOTES/ordinance_extraction_excerpts/edina_municode_36_640.md`

## Evidence Notes

Bellevue direct `curl` returned Cloudflare `cf-mitigated: challenge` for `https://bellevue.municipal.codes/LUC/20.10.440`. The adapter retrieved the land-use-chart text and preserved the source URL.

Bainbridge direct browser-like `httpx` fetch returned 403, but Jina retrieved the static Code Publishing chapter and the harness selected the full `18.06.040` section rather than the table-of-contents stub.

Municode unauthenticated `/api` probes returned 401. The adapter retrieved the official Edina `nodeId` URL for `Sec. 36-640`, including the mini-storage warehouse principal-use language for the Planned Industrial District.

## Operator Usage

Default proof run:

```bash
cd backend
python -m scripts.retrieve_ordinance_excerpts
```

Custom target:

```bash
cd backend
python -m scripts.retrieve_ordinance_excerpts \
  --url "https://library.municode.com/mn/edina/codes/code_of_ordinances?nodeId=..." \
  --section "36-640" \
  --label "Edina PID principal uses" \
  --slug "edina_pid_principal_uses" \
  --keyword "mini-storage"
```

## Risk Register

- Jina Reader is an external dependency. If it rate-limits or changes behavior, the adapter will HALT honestly rather than emitting empty text.
- Municode native API remains gated without authentication; this PR does not create subscription/API access.
- Very large use tables may still need operator review because rendered text preserves rows but not always column geometry.
- This adapter retrieves ordinance text/excerpts. It does not solve GeoPDF zoning-map polygon extraction from PR #300.

## Recommendation

Use this adapter for the 30 queued verdict-truth candidates. Do **not** pursue Municode subscription procurement for this cohort unless Jina access becomes unavailable or license/commercial-use review rejects the reader fallback.
