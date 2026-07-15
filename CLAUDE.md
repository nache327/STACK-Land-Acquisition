# ParcelLogic / STACK Land-Acquisition — working playbook

Repo: **STACK-Land-Acquisition** (this local dir is `zoning-finder`). Prod API base
`https://capable-serenity-production-0d1a.up.railway.app` (Railway service = ParcelLogic).
Real DB = Supabase (scripts use `scripts/_db.get_sync_dsn()` — asyncpg, session-mode port 5432).
**Never hardcode/print credentials.** Commit + push when work is done; open a PR (merge-gated — Nache merges
via UI → Railway auto-deploys). PR link form: `.../STACK-Land-Acquisition/pull/new/<branch>`.

## The one metric — wealth-gated NEEDLE
The product's only number is *parcels you'd confidently hand to someone for outreach*. Report the
**wealth-gated needle count**, never raw coverage:

> NEEDLE = grounded **human** `self_storage ∈ {permitted, conditional}` AND `acres ≥ 1.5` AND dt=10
> `parcel_ring_metrics.median_home_value ≥ 475000` AND `median_hhi ≥ 100000`.

**Do NOT use `homes_over_1m/2m/5m`** — NULL everywhere (scoring bonus, not the gate); querying them returns a
false 0. Industrial land *outside* the wealth ring (Waukegan, Gurnee, Lake Zurich's Rand Rd corridor) grounds
correctly but yields ~0 needles — a **correct no-op**, not a gap. Loudoun VA (1,153) is the benchmark; Norfolk MA
(1,331) is currently #1.

## Per-muni grounding loop (the 7 steps)
1. **Fetch** the ordinance — try curl+UA / backing APIs BEFORE declaring "no source" (see Fetch unlocks).
2. **Rebind** only if MA/assessor codes mismatch districts: add a NEW `backend/scripts/rebind_configs/<muni>.json`
   (never edit a shared dict) → `backfill_zoning_from_districts.py` dry-run → gates a/b/d PASS → apply; else route
   to the town-GIS layer (Braintree pattern). PA/NY parcels are usually spatially bound → no rebind.
3. **Parse** the use table under the 2.3 guards (`app/services/ordinance_parser.py`).
4. **Self-verify** vs the source: column alignment, closed-list clause, named-use definitions.
5. **Escalate** genuine ambiguities to your OWN `outputs/_exceptions_<X>.md` (never the shared queue).
6. **Apply** muni-scoped verdicts via a per-muni `_apply_<muni>.py` (`human_reviewed=true`, verbatim citations).
   Verify rows with a SELECT before declaring done. Do NOT re-score yet.
7. **One county re-score** at batch end (advisory-locked) + `verify_batch.py` must be CLEAN / gate must PASS.

## Discipline (the "catch" conventions — the gate can't see these)
- **#37 verbatim basis** — ground on the ordinance's literal words; don't infer a code's meaning.
- **#38 wrong-jurisdiction / mislabeled family** — verify a GIS layer's codes + geometry match the town's CURRENT
  ordinance before trusting it. Note: `I`/`I-2` is often **Institutional**, not Industrial; `LI` is the industrial
  needle. `M-1/2/3` may be **Multifamily**, not Manufacturing (Tarrytown).
- **#42 verify-before-declare** — show DB rows; never claim a result you didn't query.
- **#57 affirmative-provision** beats silence; **#58 closed-list sweep** — re-test every inferred/unnamed use;
  demote what fits no named use.
- **`lgc-unnamed → prohibited`** — luxury_garage_condo is prohibited unless a real garage use is NAMED; never let
  it outrank a prohibited `self_storage` (the postingest gate hard-fails that sibling leak).
- **warehouse-by-right zone ⇒ ss/mw conditional** (established convention).
- Use the **CURRENT adopted bylaw**, never a stale/draft copy (Hudson trap). **Demote, don't delete** gated rows.
- **`municipality` MUST equal `parcels.city` EXACTLY** — the buybox join is case-sensitive. MA = UPPERCASE
  (`NEEDHAM`), PA/NJ/NY/CT = mixed-case with suffix (`Bensalem Township`, `Franklin township`). `SELECT DISTINCT
  city FROM parcels WHERE jurisdiction_id=<jid>` first. Wrong case silently scores 0.
- **In-app Zoning Verifier: FIXED + deployed, freeze LIFTED 2026-07-15** (#494). It now requires a town
  (canonical `parcels.city` selector) and threads `municipality` through apply-correction, hard-rejecting an
  unscoped write except for single-place jurisdictions. Round-trip verified on prod (verdict → SELECT →
  `municipality`=exact `parcels.city`). In-app re-verification is safe again; scripts remain fine too. Still
  match `parcels.city` casing exactly (see the rule above).

## Fetch unlocks (try before escalating "no source")
- **eCode360** (403s WebFetch) → `curl -sL -A "<browser UA>"`: section HTML + `/attachment/*.pdf`. For coded PA
  chapters, the print endpoint `ecode360.com/print/{CLIENTCODE}?guid={ZONING_CHAPTER_GUID}&children=true` renders a
  whole chapter in one ~2MB fetch (detect self-storage by NAME — "Miniwarehouse" — codes differ per town).
- **Municode** (SPA 403s) → `api.municode.com/CodesContent?jobId&nodeId&productId` returns JSON.
- **amlegal** → curl+UA. **GIS-Consortium** token-gated `ags.gisconsortium.org/.../<F>/*` → anonymous proxy
  `utility.arcgis.com/usrsvcs/servers/<guid>/rest/services/<F>/AGOL_<F>_Project/MapServer` (guid from the village
  community-map-viewer). MAPC/NMCOG/town ArcGIS for MA rebinds.

## Standard scripts (run these — don't hand-write SQL)
- `python scripts/verify_batch.py --jurisdiction <jid>` — one-shot batch verify: casing check + needle tally by
  town + on-needle CoStar + post-ingest gate. Exit 0 = CLEAN. **Run at batch end; paste its output as your report.**
- `python scripts/postingest_gate.py --jurisdiction <jid>` — hard anti-poison gate (URL codes, domination,
  unclear-masquerade, catch-#58 sibling leak); exits nonzero on failure.
- `python scripts/backfill_zoning_from_districts.py` — district rebind (per-muni `rebind_configs/*.json`).
- `python scripts/_match_listings_direct.py <jid>` — CoStar matcher; use INSTEAD of the Railway worker endpoint
  (the worker dies on county-sized geocode tiers — catch #25).
- CoStar ingest = `POST /api/listings/upload` (multipart `file`+`source=costar`+`jurisdiction_id`) THEN
  `_match_listings_direct.py <jid>`.

## Parallel-session discipline
Worktree per session (`git worktree`, own `.env`, same Supabase); one county per session; fresh branch off `main`
per batch; muni-scoped writes are parallel-safe; ONE advisory-locked re-score per county at batch end; per-session
exception files. `docs/PARALLEL_SESSIONS_RUNBOOK.md` is the long-form version. Persistent coordinator memory lives
in `~/.claude/projects/.../memory/`.

## Efficiency (Nache steer, 2026-07-13): stay on Opus 4.8; cut orchestration WASTE only
Verdict accuracy > model savings (the gate can't catch a plausible-but-wrong verdict). Do NOT downgrade the model or
reduce oversight. Save tokens by: (1) **no live status-polling** — background long jobs and report once on the
completion notification; (2) **`verify_batch.py` instead of ad-hoc SQL**; (3) this file so sessions don't re-derive
the playbook. Bigger batches are fine (the gate + verify_batch run per batch regardless).
