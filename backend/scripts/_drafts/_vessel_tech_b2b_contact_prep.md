# Vessel Tech B2B Contact Prep — DIAGNOSTIC

Date: 2026-06-24
Branch: `adarench/vessel-tech-b2b-prep`
Author: Discovery + Coverage Expansion lane
Status: **READ-ONLY DIAGNOSTIC. DO NOT MERGE.** Material for Master's B2B outreach packet.

Companion to PR #336 (merged) — `backend/scripts/_drafts/_vessel_tech_arcgis_scan.md`.

## Why this prep doc exists

PR #336 identified 47/47 zoning Feature Services on Vessel Technologies' ArcGIS org (`KX6JS016gWFWiY6Y`) as token-gated. Master is the executive who would carry the B2B ask. This doc deepens the auth-route diagnosis, identifies the right contact channel + person, surfaces a material new blocker, and drafts the email Master can send (or adapt).

## Headline finding — Material new blocker

**Vessel Tech's ArcGIS Online subscription appears disabled.** When probing item-level metadata and the `/data` endpoint, the API returns:

```json
{"error":{"code":403,"messageCode":"SB_0005",
 "message":"Subscription is disabled, the item is not accessible"}}
```

This is a stronger blocker than "needs a token." Even if Vessel issues a valid Esri token, items in a subscription-disabled org may continue to return 403 until the subscription is reactivated. The most recent item modification across all 47 layers is **2024-03-23**, with no updates in 15+ months — consistent with an internal GIS function that was paused or wound down.

**Implication for Master's ask:** the contact request should propose either:
1. **Direct data export** (Shapefile / GeoJSON / FileGDB / SQLite) of the 3 pilot layers, OR
2. **Account reactivation + scoped read access** if Vessel still values keeping the GIS function live.

Asking only for "a token" risks getting "yes, here's a token" — followed by 403s and a stalled pilot.

## Auth method — ArcGIS Online standard

Per portal probe (`/sharing/rest/portals/KX6JS016gWFWiY6Y`):

| Field | Value |
|---|---|
| Provider | `arcgis` (Esri Identity Manager native) |
| All SSL | `true` |
| Portal host | `www.arcgis.com` (urlKey: `vesseltechnologi`) |
| Custom domain | `vesseltechnologi.maps.arcgis.com` (live, HTTP 200) |
| SAML enabled | not advertised in public portal metadata |
| Subscription state | **disabled / lapsed** (per item-level 403) |

Token-acquisition path for tokened FeatureServer reads:

1. Vessel issues a named Esri ArcGIS Online user account within their org (`KX6JS016gWFWiY6Y`) for a STACK email, OR
2. Vessel adds STACK to a shared ArcGIS Online group that includes the 47 items, OR
3. Vessel exports the underlying datasets and shares them directly (Shapefile / GeoJSON / SQLite / FileGDB).

Routes 1-2 require the subscription to be reactivated. Route 3 does not — it only needs Vessel's internal team to extract source files they already own. **Recommend leading with Route 3.**

API key / app-token route is not surfaced in their org metadata — Vessel does not appear to publish a developer credentials program. This is a single-tenant internal Esri ArcGIS Online corporate tenant.

## Item ownership — Single named user

| Probe | Result |
|---|---|
| `/sharing/rest/search?q=orgid:KX6JS016gWFWiY6Y type:"Feature Service" zoning` | **47 results, single owner** |
| Owner username | `awalter_vesseltechnologies` |
| Profile fullName / email | empty / hidden (privacy filter applied) |
| User created | 2023-08-16 |
| User last modified | 2024-06-29 |
| Auth provider | `arcgis` (Esri-native, not federated SSO) |

Read: `awalter_vesseltechnologies` is the GIS analyst who built all 47 layers. Most likely a first-initial + last name handle ("A. Walter" at Vessel). They are the technical person who could approve and execute either a tokened-access path or an export. They are *not* a public-facing contact and should not be cold-emailed — instead, name them inside the email to the legal / partnerships contact so Vessel can route internally.

## Company contact channels

Probed `vesseltechnologies.com`:

| Channel | Endpoint | Recommendation |
|---|---|---|
| Legal email | `legal@myvessel.com` | **Primary email contact.** Only public Vessel-domain email; covers business/data partnerships. |
| Main line | `+1 (212) 899-5353` (NYC) | Backup phone if email gets no reply in 7 days. |
| Contact form | `vesseltechnologies.com/contact` | Has intake options including "Offer Us Land" and "Purchase a Vessel System" — the cleanest non-email channel. No "Partnership / Data" option, so select most-appropriate freeform. |
| PR | `jakemalcynsky@gbpr.com` (Gaffney Bennett PR) | **Do not use.** Wrong channel — they handle press, not data partnerships. |
| LinkedIn | `linkedin.com/company/vessel-technologies-inc` | Backup channel if Master prefers warm outreach via mutual connections. |

**Business context:** Vessel Technologies builds modular / attainably-priced housing systems ("Vessel System"). Their 47 NJ/CT zoning layers were built by an internal GIS team for site-selection underwriting, not as a data product. This is a *non-strategic* internal dataset for them — which means the ask is low-stakes (they're not protecting commercial value) but the ask must be routed to someone who understands what we're requesting (not the PR firm).

## Per-layer data activity signal

All 47 layers were created 2023-08 through 2024-03, with **no modifications after 2024-03-23**. Sample top-viewed and most-recently-modified items:

| Layer | Views (lifetime) | Last modified |
|---|---:|---|
| Granby CT Zoning | 245 | 2023-12-31 |
| Ewing Zoning | 236 | 2023-10-27 |
| Oxford CT Zoning | 226 | 2024-01-10 |
| Mount Laurel NJ Zoning (pilot rank 1) | 69 | 2023-11-15 |
| Westport CT Zoning (pilot rank 2) | 190 | 2024-01-12 |
| New Canaan CT Zoning (pilot rank 3) | 196 | 2023-12-31 |
| Orange CT Zoning (most-recently-modified) | 119 | 2024-03-23 |

Read: views are 50-250 range across the board, consistent with internal-team-only usage. No item is heavily-trafficked, which suggests *low cost to Vessel* of granting export access — they are not relying on these as live operational data.

## Data shape — Cannot sample anonymously

| Item | Public item JSON | `/data` endpoint | FeatureServer root |
|---|---|---|---|
| `Mount Laurel NJ Zoning` (`edbd183e86e842ae8de583250f5a4095`) | 403 Subscription disabled | 403 Subscription disabled | 499 Token Required |
| `Westport CT Zoning` (`1c74b596a68d4f378ee5f99590e43992`) | 403 Subscription disabled | 403 Subscription disabled | 499 Token Required |
| `New Canaan CT Zoning` (`83e649d0030f4d5bbbea43995d10c53a`) | 403 Subscription disabled | 403 Subscription disabled | 499 Token Required |

Service-Definition (`.sd`) sibling items are also 403. There is **no anonymous path to a field-schema or polygon-count sample.** Master's ask must include a 5-row attribute sample per pilot layer to unblock the per-muni Class B QA gate.

## Field-shape inference (low confidence)

Without samples, the safest assumption from Esri Hosted Feature Service convention + per-muni Class B pattern observed across PR #335 (Hingham/MAPC), PR #361 (CT v2), and PR #369 (Burlington):

| Likely field | Type | Notes |
|---|---|---|
| `OBJECTID` | int | Standard ArcGIS PK |
| `Zone` / `ZONE` / `ZONING` / `zoning_code` | text | Bylaw zone code (high-confidence guess from CT/NJ peer adapters) |
| `Description` / `District_Name` | text | Plain-language zone name |
| `Shape__Area`, `Shape__Length` | double | Standard geometry derivatives |

Polygon counts per layer: **unknown — cannot be sampled.** CT per-muni peers observed in nache adapters typically range from 8-40 zoning districts per town. Treat 15 as a planning median for estimate sizing.

## Estimated polygon unlock if access granted

Using the PR #336 ranking + 58-list overlap analysis already in the scan doc:

| Scenario | Munis unlocked | Polygon estimate (15 median) | 58-list +1 ops |
|---|---:|---:|---:|
| Top-3 pilot (Mount Laurel, Westport, New Canaan) | 3 | ~45 polygons | **+3** (all three are direct 58-list / deferred-wave overlaps) |
| Top-3 + Fairfield breadth (Fairfield, Norwalk) | 5 | ~75 polygons | +3 to +5 (depending on whether Master counts Fairfield County breadth as named-center ops) |
| All 47 layers | 47 munis (22 NJ, 25 CT) | ~705 polygons | +3 to +5 confirmed named-center ops + speculative breadth — most NJ titles (Bloomfield, Belleville, Newark, Jersey City, Passaic, Plainfield, Carteret, East Orange, Orange, Union City, Linden) and most CT non-Fairfield titles (Avon, Bethel, Bloomfield, Cheshire, Cromwell, Essex, Farmington, Glastonbury, Granby, Groton, Hamden, Middletown, Milford, New Haven, Old Saybrook, Orange, Oxford, Rocky Hill, Simsbury, South Windsor, Wallingford, West Hartford, Wethersfield, Windsor) are NOT canonical wealth-pocket ops — they would only score if STACK adopts a county-breadth strategy. |

**Realistic expected lift if Master secures top-3 access: +3 ops** (Mount Laurel NJ wealth-tail of Burlington; Westport CT + New Canaan CT Fairfield-wave deferred sources).

**Speculative ceiling if Master secures all 47 + STACK adopts county-breadth: +5 to +12 ops** (Mount Laurel, Westport, New Canaan, Fairfield, Norwalk, Trumbull, Shelton, Stratford, Newtown as Fairfield County breadth; Hackensack as Bergen NJ breadth).

This is metadata-only sizing. Each muni still needs parcel substrate + jurisdiction registration + matrix citations even after Vessel hands over polygons.

## Pricing / tier signal

**None visible.** Vessel does not publish a data API, pricing page, partnership program, or developer portal. This is an internal corporate ArcGIS Online tenant, not a commercial data product.

For Master's ask: **frame as a non-monetary data-sharing partnership**, not a license purchase. Offer reciprocity — STACK can share aggregated underwriting signal back to Vessel for the markets we both operate in (Vessel as a housing developer also benefits from clean zoning underwriting in NJ/CT).

## Suggested email — for Master to send / adapt

**To:** `legal@myvessel.com`
**Subject:** Data-sharing inquiry: STACK Land Acquisition — Vessel's NJ/CT municipal zoning layers

```
Hi Vessel team,

I'm Master at STACK Land Acquisition. We're a land-acquisition
underwriting platform — we ingest municipal zoning and parcel
data for the U.S. residential development market, with a current
focus on the NJ and CT South Shore / Fairfield County corridors.

While scoping public ArcGIS Online sources for our coverage
expansion, we found that Vessel Technologies maintains a set of
47 high-quality per-municipality zoning Feature Services for NJ
and CT (org id KX6JS016gWFWiY6Y, owner awalter_vesseltechnologies).
These were last refreshed March 2024.

The services are currently returning "Subscription is disabled"
to anonymous reads, so we can't ingest them on a public path.
We'd like to explore a B2B data-sharing arrangement.

Specifically, the three layers most useful to our underwriting
roadmap are:

  1. Mount Laurel NJ Zoning  — direct overlap with our Burlington
     County NJ acquisition wave
  2. Westport CT Zoning      — Fairfield County add-on (currently
     blocked at AxisGIS in our public-source path)
  3. New Canaan CT Zoning    — Fairfield County add-on (currently
     blocked at adopted-regs split in our public-source path)

What would work for us:

  • A one-time export of these three layers (Shapefile, GeoJSON,
    FileGDB, or SQLite — any of those work), OR
  • Reactivated tokened read access to the FeatureServer for an
    STACK ArcGIS Online identity, OR
  • A 5-row attribute sample for each so our team can confirm the
    field schema matches our adapter pattern, ahead of a fuller
    arrangement.

In return, STACK is happy to:

  • Share the cleaned/normalized zoning matrix we derive in these
    municipalities back to Vessel for your own site-selection use,
  • Cite Vessel as a source-of-record in our underwriting outputs
    where these layers are the primitive,
  • Discuss commercial terms if Vessel prefers a paid arrangement
    over reciprocal sharing.

Happy to schedule a 30-minute call if useful. If this should go to
a different team (partnerships, BD, GIS lead), please point us in
the right direction and I'll re-route directly.

Thanks,
Master
STACK Land Acquisition
[contact]
```

Notes for Master:
- Substitute the bracketed `[contact]` with preferred reply email / phone.
- If `legal@myvessel.com` does not reply within 7 business days, escalate via the contact form at `vesseltechnologies.com/contact` (intake category: "Other"), and include the same content. Reference the named GIS owner `awalter_vesseltechnologies` so the routing team can find them internally.
- Do NOT contact `jakemalcynsky@gbpr.com` — that's the PR agency, not the data team.

## Risk register update vs PR #336

| New risk vs PR #336 | Impact | Mitigation |
|---|---|---|
| Subscription disabled state | Tokens may not unlock items until reactivation | Ask for direct export as Plan A, tokened access as Plan B |
| Single technical owner (awalter) may have left the company | Internal routing may fail if owner is not at Vessel anymore | Name owner in email so legal can confirm/route; if owner gone, request Vessel point to whoever inherited GIS responsibility |
| 15+ months no activity on any layer | Vessel may have wound down internal GIS function | Lowers Vessel's cost to share; raises risk that no one internally knows where the source data lives. Ask explicitly for "source files you used to build these layers" not just the published FeatureServer extract |
| No commercial tier exists | No standard contract template | Offer reciprocal data-sharing first; only escalate to paid terms if Vessel asks |

## What does NOT change vs PR #336

- 47-title inventory: unchanged. PR #336's full table remains authoritative.
- Top-3 pilot ranking (Mount Laurel, Westport, New Canaan): unchanged.
- 58-list overlap analysis: unchanged.
- Class classification (Class B per-muni FeatureServer, tokened/private): unchanged.
- Lane A dispatch posture (HALT for anonymous; PURSUE for B2B): unchanged.

## Stand-down

Per user budget: **HALT-AND-REPORT.** No further Vessel Tech probing absent a response from Vessel.

Re-engagement criteria:
- Vessel replies to Master's email → activate Lane A pilot for whichever pilot layer(s) Vessel grants access to
- Vessel does not reply in 14 days → escalate to phone (`+1 212 899 5353`) once, then formally close as "non-responsive B2B" in the source registry
- If Vessel offers paid commercial terms → bounce to Master to evaluate ROI vs +3 ops ceiling

## Scope guards honored

- Read-only HTTP probes only. No writes to any external system. No outreach sent from this lane.
- No ingest, no jurisdiction registration, no DB rows touched.
- Email is a *draft for Master* — not authorized to be sent from this lane.
