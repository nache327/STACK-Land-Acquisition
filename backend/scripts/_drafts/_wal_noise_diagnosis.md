# Worth a Look noise diagnosis (2026-06-15, READ-ONLY)

## Premise vs reality
Premise: "~10 SLCo no-price teasers/day flooding the inbox." **Actual current state (≥70, current
listings):** Worth a Look matches **7 listings, all Salt Lake County, UT — 2 no-price, 5 priced.**
`daily_email_top_n=10`. So the inbox gets ≤7 WAL items/day, of which **2 are no-price**. The "flood"
is stale — it's a 2-listing trim, not 10.

## Design tension (flag for Nache)
No-price is an **intentional soft flag** in the digest — `(lst.sale_price IS NULL) AS soft_no_price`
([daily_email.py](backend/app/workers/daily_email.py)). Worth a Look is the *lower-bar* tier (vs
Storage Needles' hard gate), so surfacing unpriced "worth a look anyway" listings may be by design.
Tightening WAL to require a price is a **product call**, not a bug fix.

## What I built (PR `parcellogic/wal-require-price`)
A generic, reusable, **off-by-default** filter option `requirePriced` in `_top_parcels_for_filter`
(mirrors `requireListed`): when set, drops listings with `sale_price NULL/0` instead of surfacing
them behind the no-price soft flag. +3 regression tests (clause present, param true when set,
defaults false → current behavior preserved). **No behavior change until the flag is set on a
filter** — so merging the code is safe.

## To actually tighten Worth a Look (Nache's decision — one-line data change)
```sql
UPDATE buybox_filters
SET filter_json = filter_json || '{"requirePriced": true}'::jsonb
WHERE name = 'Worth a Look';
```
Impact today: removes the **2** no-price SLCo listings from the WAL digest; keeps the 5 priced.
Recommendation: low urgency (2 listings), but harmless future-proofing — enable if the no-price
teasers are unwanted; leave off if WAL is meant to be the catch-all soft tier.
