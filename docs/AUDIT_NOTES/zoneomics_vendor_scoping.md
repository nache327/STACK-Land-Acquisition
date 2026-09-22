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
- **2026-09-22: sales/demo call #1 (partial — more calls to come).** Findings below are
  from the vendor's own live demo, not marketing copy.

### Call #1 findings (2026-09-22)

**NEW — free `jurisdictions` endpoint (the most valuable thing on the call).**
Does not consume credits. Per jurisdiction it returns **the date Zoneomics last
reviewed it for a zone-code change AND the date it last actually changed** (demoed on
Alpine UT: reviewed 4 days prior, last changed Feb 5). This is a drift signal covering
*every* jurisdiction — including the PDF-only / non-eCode360 / non-Municode towns where
our own `ordinance_sentinel.py` is weakest. Complement, not replacement: their "last
changed" is *their detection* date, so it lags the town, and it is jurisdiction-level,
not chapter-level. **Action: get endpoint docs + confirm no license restriction on
scheduled polling.** Candidate as a second-signal input to the sentinel for the ~8% of
monitored munis on hosts we can't fingerprint well.

**PLU confirmed as verbatim ordinance text, NOT a per-use verdict.** Rep: "these are all
verbatim from the muni code… we just don't want anything lost in context." Buckets seen:
`as_of_right`, `conditional`, and per the rep also `special`, `accessory`, `prohibited` —
"whatever you're getting back is everything **that we found** in the zone code." That
last clause is decisive: **absence in their payload ≠ prohibited in the ordinance**, so
prohibited-by-omission (catch #58 closed-list sweep) cannot be derived from their data.
Confirms the standing no-buy-as-verdict-source ruling; the interpretation layer stays ours.

**Response shape** (one call per address or lat/lng returns all of it): `city_id`,
`city_name` = *the jurisdiction actually governing the address* (flags e.g. County
Unincorporated and links to that code — useful for our county-vs-muni ambiguity),
zone code / name / type / subtype, optional muni intent guide, PLU buckets, development
controls split **standard** (numeric) vs **non-standard** (carries the conditionality
text, e.g. "accessory building shall be set back not less than five feet from the main
building"), covering setbacks, max height, max DU/acre, impervious coverage, open space,
landscaping, min lot width, front/side/rear yards. Plus parcel data: lat/lng, address,
current land use, area, and the **parcel** boundary polygon.

**Geometry — CONFIRMED as zoning-district boundaries, not parcel outlines.** Asked
directly on the call ("is that showing the boundary of the zone?" — "Yes… it's the
boundary of this BC zone, that's why there are so many coordinates"). They also serve a
**tiling layer** for visualization. This is the one vendor asset with real potential
value to us: **zoning district polygons for bind-blocked munis** (Nassau NY villages,
Hudson MA, Cook/DuPage IL, Redding CT, Bloomfield/Franklin) where no public GIS layer
exists and binding is the blocker. Still to confirm: can district polygons be pulled for
a whole municipality in bulk, what is the per-muni provenance and vintage, and does the
license permit storing them and using them to bind our own parcels (vs. display only).
Any adopted geometry still passes the existing #38 dry-run % bind gates.

**Owner data** also returned (LLC name + address) — not a driver for us; owner mailing is
already ~93% backfilled in-house.

**Municipality-level query exists** — the rep demoed searching by municipality, not only
by address ("or you can do the municipality itself… doesn't make a difference"). **This is
the pricing crux: if one municipality query returns every zone in the town, our cost model
collapses from ~30–40 lookups/muni to ~1.** Must confirm what a muni-level call returns
and how it is metered.

**Commercial model.** Priced on **monthly address lookups**; 1 lookup = 1 API call = the
full payload above. Trial key offered with access to all endpoints; they want a monthly
volume estimate before quoting. Bulk data exists but the rep steered us away from it —
note he assumed we *receive* vetted deals and only verify them, which is wrong (we do
bulk discovery). **Correct the framing when quoting: we query ~1 point per zoning
district per town (~30–40 calls/muni), a few thousand to open a market, low steady-state
after** — otherwise the quote will be built on the wrong usage shape.

**Still unanswered after call #1:** (1) the written redistribution authorization — the
hard gate; (2) coverage check against our ~200-muni list; (3) actual price; (4) measured
accuracy / error direction; (5) the Hudson MA (Nov-2023 recodification) and Chelmsford MA
(CBLT added Oct-2025) staleness probes; (6) whether self-storage / mini-warehouse is a
named class in `plu-tags`; (7) zoning-district polygon availability.

### Trial terms as offered (2026-09-22)
- **Production key: 20 address-or-lat/lng lookups, nationwide.** Scarce — every credit
  must be spent on a question nothing else can answer.
- **Sandbox key: ALL endpoints, no limits, geolocked to Redondo Beach CA.** Build and
  debug the client here; it consumes no production credits.
- **`zoneDetail` (point) is the main endpoint**, and **all output fields come back for
  one credit** — so always request everything (zoning + plu + plu-tags + controls +
  gde-controls + parcels/boundary). They will send a sample call URL.
- `jurisdictions` endpoint is **free / uncredited** (see above).

### The 20-credit benchmark plan (replaces the 60–100-pair design, which the trial
cannot fund)

**Spend zero credits on anything these can answer:**
- *Coverage roll-call* of our ~200-muni target list → free `jurisdictions` endpoint.
- *Freshness / staleness probes* (Hudson MA Nov-2023 recodification; Chelmsford MA CBLT
  added Oct-2025) → free `jurisdictions` endpoint's last-reviewed / last-changed dates.
- *Client code, field mapping, parser, response logging* → sandbox (Redondo Beach).

**Then spend the 20 production lookups, by lat/lng taken from the centroid of a parcel we
already hold in the target zone (never a typed address — avoids their geocoder as a
confound). Log every raw response to disk; a credit must never be spent twice.**

| # | Purpose | What it decides |
|---|---|---|
| 5 | **Geometry unlock** — one point in each bind-blocked muni (a Nassau NY village, Hudson MA, a Cook/DuPage IL muni, Redding CT, Bloomfield Twp MI) | Do they hold district polygons where **no public GIS layer exists**? This is the only vendor asset that would unlock *new* markets rather than duplicate work. Highest value per credit. |
| 2 | **Prohibited-by-omission** zones (our human ruled prohibited via closed-list sweep) | Do they return silence or an explicit prohibition? Silence-where-human-ruled is scored as its own outcome class, not as agreement. |
| 2 | **Conditional** self-storage zones | Agreement on the middle case. |
| 2 | **Permitted** self-storage zones | Sanity check on the easy case. |
| 2 | **#38 trap zones** (`I`/`I-2` = Institutional, `M-1` = Multifamily — Tarrytown) | Does their zone typing reproduce the mislabel that would poison a code-level screen? |
| 1 | **Named-garage / LGC** zone | Whether the LGC lane is visible to them at all. |
| 2 | **Known-amendment parcels** (Chelmsford CBLT; one Hudson post-recodification zone) | Whether a recent adopted change is actually reflected in zone-level data. |
| 4 | **Reserve** | Follow-ups triggered by surprises in the first 16. |

Sample selection must **exclude any muni the old `batch_populate_ordinances.py` scraper
touched** (self-agreement contamination) — all UT jurisdictions in particular.

### Flag: the license gate is STILL unanswered after call #1
Nothing in the demo addressed written authorization for verdict-derived distribution.
It remains decision rule #1 and it can kill the purchase regardless of how the benchmark
scores. **Get it in writing before investing build time in the client.**

### Flag: discount the vendor's own value pitch
The rep's closing framing was that this "saves your daily compute through Claude looking
up the codes." That is not our cost center — the fetch step is largely solved by the
banked unlocks, and our real cost is human adjudication, which this does not touch. The
two claims worth testing are the ones above: **bind-blocked district geometry** and a
**second freshness signal** for munis our primary-source sentinel can't fingerprint.

- (append trial results / final buy-no-buy here)
