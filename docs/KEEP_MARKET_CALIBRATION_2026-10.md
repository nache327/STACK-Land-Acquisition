# Keep market calibration — what sells, where, and for how much (Phase A)

*2026-10-15 · STACK internal · data + scripts in `outputs/keep_calibration/`*

## Bottom line

1. **Your thesis holds: the same model in nicer areas sells for much more.** Two clean, real-deed tests:
   - **Location alone:** Toy Barn — same developer, same product, same county, same years — sold **$446/SF in
     Scottsdale vs $309/SF in Chandler (+45%)**.
   - **Product alone:** in Chandler in 2024–25, **Toy Barn $309/SF vs LuxeLocker $196/SF (+57%)**.
   - Stacked, a nicer product in a wealthier location (Toy Barn Scottsdale) sold for more than twice LuxeLocker's Chandler price.
2. **What predicts price is how much real wealth surrounds the site — not the median home value or income.**
   The best signal is the **share of homes worth $1M+ within a 20-minute drive**. Next come drive time to the
   nearest $1M+ neighborhood and the seasonal / second-home share. ParcelLogic's current garage-condo gate (median
   home value ≥ $475K) is a weak predictor, and it **fails campuses that sold out**: both Lake Havasu sites,
   Henderson, Motocave, Motor Enclave and Big Door all fail it.
3. **Speed is not the problem in most markets.** Almost every campus since 2018 sold half its units within 1–3
   months of first closing, and most presold. No demographic reliably predicts velocity. The slow ones are
   execution or oversupply stories (Prescott, Reno, Glendale, Richland, Mesquite). The one hint: more **younger**
   affluent households (45–64 vs 65+) → faster sales.
4. **The "works" buyer is not visible in deeds.** Only **3–4% of LuxeLocker units went to operating businesses**;
   about 75% went to individuals and trusts. Tradesmen buying in their own name are invisible, so this is a floor,
   not a ceiling. Utah flex condos ask **$315–420/SF** for ~1,000–1,200 SF bays, so works units don't have to be the
   cheap tier.
5. **Bigger units don't earn more per SF at the nicer projects** (flat or lower at Toy Barn, Big Door, Motocave).
   Price comes from **location + finish/clubhouse product**, not unit size. The mix is a velocity and risk dial,
   not a price lever.

## The evidence

Prices are developer (first) sales from county deed records. "Ratio" = $/SF ÷ local typical home $/SF in the sale
year (Zillow county value ÷ 1,800 SF). It strips out timing so a 2021 sale isn't read as a cheap market.

| Campus | Median $/SF | Year | Ratio | $1M+ homes within 20 min | Drive to wealth center |
|---|---|---|---|---|---|
| Toy Barn Scottsdale Airpark | $298 | 2019 | **1.81** | 11.8% | 23 min |
| Auto ClubHouse Jupiter | $463 | 2026 | **1.77** | 15.6% | 50 min |
| Toy Barn Scottsdale (Helm) | $450 | 2023 | **1.74** | 13.9% | 25 min |
| Motor Enclave Tampa | $385 | 2023 | **1.73** | 0.7% ⚠ | 29 min |
| Toy Barn Dove Valley | $419 | 2026 | 1.64 | 16.7% | 36 min |
| Big Door Mundelein | $238 | 2021 | 1.44 | 5.5% | 35 min |
| Motocave St. Pete | $313 | 2024 | 1.38 | 5.6% | 20 min |
| Luxe Dream Lakewood Ranch | $307 | 2024 | 1.21 | 4.4% | 38 min |
| Toy Barn Chandler North | $309 | 2025 | 1.20 | 3.0% | 39 min |
| Toy Barn Lone Mtn / North / Peak View | $117–232 | 2013–22 | 0.79–1.13 | 9–13% | 34–36 min |
| LuxeLocker (11 campuses) | $103–253 | 2020–26 | **0.46–0.99** | 0.6–4.7% | 27–184 min |

⚠ Motor Enclave is the outlier: a top-tier ratio with a thin pool. Its product (many finished "villa" units at
$820–940/SF) and a site 1–2 miles off the wealth core both play a part. It needs a closer look before Phase B.

**Which signals line up with price** (rank correlation with the ratio, 26 campuses; directional, not a fitted model):
**$1M+ home share +0.56**, $200K-household share +0.48, wealth-center drive time −0.45, seasonal-home share +0.44,
count of $200K households +0.30, **today's median-home-value gate +0.28**, contractor / self-employed counts ≈ 0.

**Buyer profile** (Toy Barn owner lists, aggregate only): median age 61–68; 13–35% under 60; 12–24% mail from out of
state (snowbirds / second homes); 14–57% entity or trust owners. The East Valley (Chandler) list is the youngest and
the most business-heavy.

## Texas: the speed test (Garages of America, 14 campuses)

Texas doesn't publish sale prices: today's asks run ~$300–400/SF including the mezzanine, and developer starting
prices run from the mid-$200s to the mid-$400s. But the county rolls date every unit leaving the developer, so this
is our best **velocity** comparison: one operator, one product, different locations.

| Campus | Drive to wealth center | $1M+ homes 20 min | Months to 50% / 90% sold |
|---|---|---|---|
| Dallas Storey Ln | 20 min | 8.6% | **1.9 / 5.0** |
| Carrollton I | 20 min | 5.5% | 7.4 / 13.6 |
| Frisco II | 29 min | 4.9% | 4.8 / — (43 of 52 in ~14 mo) |
| Katy | 30 min | 1.6% | 3.0 (bulk buyer) / 27 |
| Lakeway | 39 min | 18.0% | 2.4 / 23 |
| Roanoke | 41 min | 8.4% | ≈21 / ≈30 (year-level counts) |
| **The Woodlands / Magnolia** | **64 min** | 6.0% | **57 of 99 still unsold after ~3 years** |

**The slowest campus is the one farthest from wealth, even though its median area looks fine.** It passes most
income tests and fails only on distance. Speed falls off with distance from the money, which is the edge-of-wealth
logic. It also backs the gate finding: Dallas and Carrollton, the two fastest sellers, both FAIL today's ParcelLogic gate.

**Spring Hill sits 57 minutes from its wealth center, Woodlands territory.** That is a velocity warning on top of
the price band below, and one more reason to price it as a cheap, fast LuxeLocker-style campus or not at all.
Westampton (38 min) and Robbinsville (36 min) sit in the Lakeway / Frisco range.

## What this says about our three test sites

Supported price = comparable campuses' ratio × the site's 2026 home $/SF. These are bands, not promises: the model is
directional, and product finish moves you within the band.

| Site | $1M+ homes 20 min | $200K HH 20 min | Wealth center | Comparable campuses | Supported $/SF | Lane |
|---|---|---|---|---|---|---|
| **Robbinsville NJ** (Rt 130) | 2.4% | 12,516 | 36 min (Princeton) | Toy Barn Chandler N, Luxe Dream, Big Door | **~$220–320**, center ≈ $270 | Edge of wealth |
| **Westampton NJ** (Rt 541/I-295) | 1.8% | 13,449 | 38 min (Princeton) | Toy Barn Chandler N, Henderson P2, Luxe Dream | **~$210–300**, center ≈ $255 | Edge of wealth, lighter |
| **Spring Hill FL** (US-19) | 0.5% | 2,317 | 57 min | Spanish Springs, Lake Havasu, Prescott, Goodyear | **~$120–190**, ≈ $210 with a strong product | Growth corridor (velocity) |

- **Spring Hill at $290 is not supported by any comparable.** $290 needs a ratio of about 1.7, which only
  Scottsdale, Jupiter and Motor Enclave achieved, all with 10–100× more nearby wealth. If Spring Hill goes ahead,
  price it as a LuxeLocker-style campus (**~$150–200/SF**, heavier on ~800 SF works bays) and win on land cost and
  speed. Its works signals are real: 8,701 self-employed filers within 15 min and +63% county contractor growth
  since 2017.
- **Westampton and Robbinsville can support The Keep's ~$300/SF only at the top of their band.** That takes the
  finished clubhouse product (Toy Barn / Motocave tier), not a LuxeLocker shell. A ~$255–270 blended plan is the safer base case.
- Cross-check: the Lake County IL listings (Luxe Corsa $288–295/SF, MotorCave $273–289/SF, both counting the
  mezzanine) land at the same ~1.3 ratio as the band's upper half.

## What to change in ParcelLogic (Phase B — proposed, awaiting your go)

1. **Replace the garage-condo median gate with depth measures, computed from the parcel itself:**
   share of $1M+ homes within 20 min (predicts price), drive time to the nearest $1M+ cluster (predicts price AND
   speed — the Texas test), and seasonal-home share. Storage scoring
   stays as it is. This should also make the Barrington hand exceptions unnecessary.
2. **Add a 20-minute drive ring** to the ring data (today it stops at 15), plus the $1M+ home counts, which also fills
   the long-empty `homes_over_1m/2m` columns nationwide.
3. **Show a price band and lane on every garage-condo card**: "Edge of wealth ~$270/SF" vs "Growth corridor ~$170/SF",
   derived from the ratio bands above.
4. **Keep works-pool and speed signals as information only,** not score points; they didn't separate campuses.
5. **Off-market list:** top-scoring unlisted by-right parcels with owner mailing.

## Caveats

- 26 campuses across 4 operator families is enough for direction, not precision. Treat bands as ±15%.
- **Product is mixed in with location:** the high-ratio campuses also sell nicer product. The Toy Barn Scottsdale vs
  Chandler pair is the only fully controlled location test.
- Results are sensitive to where the site point sits: moving Motocave's point ~400 m nearly doubled its pool. Phase B
  must measure from the parcel, not a town center.
- Maricopa keeps only each unit's latest sale, so Toy Barn developer prices come from units never resold.
- LuxeLocker's own rental of unsold units means its slow sell-outs are partly a choice.
- Texas velocity uses exact-dated transfers only; Plano, Allen and Frisco I have year-bracketed early sales, so
  their times are upper bounds (Plano reportedly sold out before completion).
- **Illinois asking prices (no recorded unit sales yet):** REVAULT Lake Zurich asks $466–477/SF ground floor =
  **$288–295/SF total incl. mezzanine** (23 of 121 sold per site; Crain's said ~40 under contract). BeSpoke Gilberts
  asks $325/SF ground = **$244/SF total**, with 21 of 26 Phase-1 units reserved on refundable deposits — notable at
  66 min from wealth, but reservations aren't closings. Always compare on the same SF basis: the gap between these
  two is 43% on ground SF but only 20% on total SF.
