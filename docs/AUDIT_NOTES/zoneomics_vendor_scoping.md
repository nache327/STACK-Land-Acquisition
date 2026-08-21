# Zoneomics vendor scoping + standing policy (2026-08-21)

Decision record for "should ParcelLogic pay for Zoneomics?" — evaluated 2026-08-20/21
(web verification of their live API docs/pricing/ToU + red-team pass + repo/infra sweep).
Template precedent: `vessel_technologies_b2b_opportunity_scoping.md`.

## Bottom line

| Question | Verdict |
|---|---|
| Zoneomics as a **verdict source** | **NO — permanent.** Cannot produce `human_reviewed=true`; needle gate ignores it; catch #37 bars mirror citations (now enforced mechanically by the postingest gate's vendor-citation check). |
| Zoneomics for **freshness** | **NO — dominated.** A vendor can only lag the primary host it scrapes. The DIY primary-source sentinel (`scripts/ordinance_sentinel.py`, shipped with this doc) monitors eCode360's New Laws badge + print-endpoint chapter hash and Municode's latest-job id directly. |
| Zoneomics for **expansion bootstrap** | **GATED, prior against buy.** One email (below); real evaluation only if written redistribution authorization + trial key arrive. Decision rule pre-registered below. |
| **Regrid Standardized Zoning** for bind-blocked geometry | **The better vendor for the one real gap.** ~13,900 munis, monthly-updated parcel-matched zoning polygons; ~$400/county research precedent (NJTPA memory). Quote for: Nassau NY villages, Hudson MA, Cook/DuPage IL, Redding CT, Bloomfield Twp/Franklin. No existing relationship (`regrid_client.py` is dark: no key, no configs, discovery path removed in `a395d20`). |

## Standing policy (answering the parked operator asks)

**Zoneomics mirror pages (`zoneomics.com/code/<muni>`) are allowed as:**
1. a **locator** (finding which chapter/section to fetch from the primary host),
2. **corroboration** of a verdict grounded on the primary source,
3. **negative-proof** ("0 occurrences … and the Zoneomics mirror" — the Parsippany pattern).

**Never as citation basis.** Citations must be verbatim from the town's primary source
(catch #37). Mirror text may be quoted in `notes` as fetch-path corroboration (the
Buffalo Grove pattern: "confirm exact wording against Municode before upgrading
conditional→permitted"). The postingest gate now HARD-FAILS any `human_reviewed=true`
row whose `citations` reference a vendor domain.

→ **Upper Dublin PA (`outputs/_exceptions_D.md`): OK to use Zoneomics as
locator/corroboration for the CR-I needle; ground and cite from amlegal/town PDF.**

## Verified vendor facts (2026-08-20)

- **API** (`api.zoneomics.com`): `zoneDetail` (point/address/polygon), `output_fields=
  with-plu|with-plu-tags|with-controls|all`. Returns zone code/name/type, per-city
  `last_updated`, and `permitted_land_uses` as three buckets — `as_of_right` /
  `conditional_uses` / `prohibited` — of **free-text ordinance extracts** (their own
  Pelham NY sample), not a normalized per-use verdict. v2 adds `/ask` (AI), `/tiles`
  (MVT), `/conditionalControls`, and `/request` ("Request Coverage" — gaps filled on
  demand; Lehi UT had no content when our scraper ran).
- **Pricing**: API plans (Starter/Pro/Growth/Enterprise) sales-gated. Public tiers
  ($92/mo Essentials, $279/mo Advanced) are the search SaaS, not API/bulk rights.
- **ToU**: internal business use OK; may **"not republish, redistribute, resell, or
  otherwise make the data available to third parties without prior written
  authorization"**; **"WE DO NOT WARRANT THE ACCURACY, COMPLETENESS OR USEFULNESS OF
  THIS INFORMATION."** ParcelLogic's product IS third-party deal lists → written
  authorization is a hard gate on any purchase.
- **History in this repo**: `scripts/batch_populate_ordinances.py` scraped their mirror
  (UT pilot; wrote 17-21 zoneomics `ordinance_url` values — repointed/NULLed 2026-08-21,
  see `scripts/_drafts/_repoint_zoneomics_ordinance_urls.py`). Three prior probes ruled
  "HALT for production / non-authoritative cross-check" (`_wayzata_alt_source_pivot.md`,
  `_ohara_pa_recovery_probe_v2.md`, Minneapolis cluster notes).

## Why the golden-sample benchmark was NOT run against their mirror
(red-team findings, kept so this isn't relitigated)
1. The mirror is not the purchasable artifact — the API's derived stance fields are.
2. The API is point-keyed; the golden set is (muni, zone)-keyed — a real benchmark
   needs zone-centroid sampling, i.e. a trial key.
3. Our golden sample is partially contaminated: munis the old scraper seeded trace to
   the mirror itself (self-agreement).
4. Their extracts are silent on our hardest verdict classes (prohibited-by-omission
   via the closed-list sweep, conditional-by-convention) — naive agreement scoring
   flatters them. Any benchmark must score "silent-where-human-ruled" separately.
5. Scraping at benchmark scale mid-negotiation is poor form and arguable ToU breach.

## Pre-registered decision rule (buy only if ALL hold)
1. Written authorization to distribute verdict-derived deal lists.
2. Price ≤ ceiling derived from realistic hours saved (fetch/bind on hostile-source
   munis only — the human adjudication step is untouched by any vendor).
3. Coverage ≥ 85% of our 58-market muni list (their list vs ours, by name).
4. Trial-key benchmark on 60–100 stratified golden pairs (contaminated munis
   excluded): false-permitted < 3% **including** silence-scored strata; agreement ≥ 85%.
5. Known-amendments probe (20–30 adoption dates from our apply scripts): reflection
   latency materially inside the sentinel's monthly cadence.
6. Geometry spot-test: vendor polygons (API, not tile-ripping) pass the existing bind
   dry-run % gates on ≥ 4/5 bind-blocked munis.
Any miss → no-buy; the DIY sentinel and free unlocks continue unaffected.

## Sales email draft (Nache sends from nn@stackstorage.us)

> **To:** info@zoneomics.com
> **Subject:** API evaluation — data licensing questions before trial
>
> Hi — we build land-acquisition software (self-storage/industrial site selection)
> and are evaluating the Zoneomics API as a data source. Before we scope a trial,
> four questions:
>
> 1. **Derived-product distribution.** Our product delivers parcel lead lists to our
>    users; zoning-use determinations in those lists are made by our own analysts
>    from primary ordinance sources, with vendor data used internally for triage.
>    Your ToU requires written authorization to make data available to third
>    parties — can you confirm in writing that this use (internal triage informing
>    our own analyst-authored determinations) is authorized, and what license tier
>    covers it?
> 2. **Trial API key** for a bounded evaluation (~100–200 zoneDetail calls against
>    municipalities where we hold independently verified ground truth).
> 3. **API pricing** at roughly 1–2k lookups/month steady-state, with occasional
>    bursts (~5k) when we open a new county.
> 4. **Coverage + freshness.** Can you run a coverage check against a list of ~200
>    specific municipalities we'd supply? And for `last_updated`: does it reflect
>    re-crawl date or detected ordinance change — and what's your typical latency
>    from a town adopting an amendment to it appearing in the API?
>
> Happy to get on a call. — Nache

## Outcome log
- 2026-08-21: policy codified; sentinel shipped (Phase A); email drafted, NOT yet sent.
- (append sales response / benchmark results / final buy-no-buy here)
