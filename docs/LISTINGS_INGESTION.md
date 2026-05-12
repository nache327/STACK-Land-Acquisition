# Listings ingestion — operator workflow

How CoStar / LoopNet / Crexi listings get from your desktop into the dashboard.

## Current architecture (Plan A — skill POSTs the API)

```
[Claude skill on your laptop]
    │
    ├── 1. logs into CoStar, runs a saved search export
    ├── 2. saves file as backend/uploads/<City>.xlsx (local copy for audit)
    └── 3. curls POST /api/listings/upload to Railway
              │
              ▼
       [FastAPI on Railway]
       parses → matches to parcels → upserts forsale_listings
                                  → fires listing_alerts worker
                                  → ListingCard shows in drawer
                                  → next digest carries the matches
```

### The skill's curl step

After the skill drops the file at `backend/uploads/<City>.xlsx`, it fires:

```bash
curl -X POST https://capable-serenity-production-0d1a.up.railway.app/api/listings/upload \
  -F "file=@C:/Users/nache_rl1pdne/zoning-finder/backend/uploads/<City>.xlsx"
```

Optional form fields:
- `source=costar` (default: auto-sniffed from column headers)
- `jurisdiction_id=<uuid>` (default: resolved from first row's city + state)

Response on success:
```json
{
  "inserted": 53,
  "updated": 0,
  "dropped": 0,
  "match_pending": 53,
  "source": "costar",
  "jurisdiction_id": "f1b280f8-1319-4071-b82d-5de21bdf8b6e",
  "parser_warnings": []
}
```

Matching runs in a background task right after the response; the ListingCard appears
in the drawer ~30s later.

## Why we chose Plan A over cloud storage (Plan B)

| Decision factor                   | Plan A (skill POSTs API) | Plan B (S3 / Dropbox poll) |
|-----------------------------------|--------------------------|----------------------------|
| Time to ship                      | One line in the skill    | New bucket + IAM + worker  |
| Failures visible immediately      | ✅ curl exit + JSON       | ❌ silent until next poll   |
| Audit trail of past exports       | ❌ only what's local      | ✅ every file kept in S3    |
| Multi-machine support             | Each machine curls       | One drop point, any source |
| Replay old uploads vs new filter  | ❌ re-run skill N times   | ✅ one bucket pass          |
| Coordination with other operators | ❌ each curls separately  | ✅ shared drop folder       |

**Why Plan A wins today**: zero infrastructure to spin up. The pipeline works in five
minutes once the skill knows the curl URL. We're proving that listings ingestion +
matching + alerts actually improve the workflow before we invest in shared storage.

**When to migrate to Plan B**: any of these triggers it
1. A curl call fails silently and we miss a listing
2. Adam or any other teammate needs to push exports too
3. We want to backfill historical listings against a new buy-box filter
4. The skill runs on more than one machine

At migration time, the backend stays the same — we just add a worker that polls
S3 and calls the same `/api/listings/upload` endpoint with each new file. The
skill's contract changes (drop to S3 instead of curl), nothing else.

## Local folder convention

`backend/uploads/` is gitignored (operator data, not source). The folder
contains your local audit copy of every export the skill has run. Keep or
prune at will — the backend only knows about files that were POSTed.

Naming convention: `<City>.xlsx` (e.g. `Lehi.xlsx`, `Marlboro.xlsx`). Skill
overwrites previous file for the same city on each refresh, since the upload
endpoint diff-merges (new listings → inserted, missing rows → dropped_at).

## Operator runbook

When you want fresh listings for a market:

1. Tell the Claude skill: "Pull fresh CoStar for-sale data for Lehi, UT"
2. Skill exports, saves to `backend/uploads/Lehi.xlsx`, curls the API
3. Wait ~1 minute
4. Open https://zoning-finder.vercel.app/dashboard/<jobId>
5. Click any parcel — if it matches a current listing, the yellow 🏷️ ListingCard
   shows price, DOM, broker company, broker name + contact

If the skill fails or the response isn't `200`:
- Check the response JSON for `parser_warnings` (column-map mismatches)
- Check Railway logs for matching errors (geocoder rate-limited, etc.)
- Re-running the same skill is safe: re-upload of an identical file produces
  0 inserts / N updates / 0 drops (idempotent by design)
