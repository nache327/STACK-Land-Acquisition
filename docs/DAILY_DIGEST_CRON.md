# Daily-digest cron setup

How to wire the daily-digest worker to actually run daily without
anyone clicking "force run." Lives on Railway as a third service
alongside `web` and `worker`.

## One-time setup (Railway dashboard)

1. **Railway project** → "+ New" → **Empty Service**
2. **Settings tab** of the new service:

   | Field | Value |
   |---|---|
   | Service Name | `cron-daily-digest` |
   | Source Repo | same repo as `web` / `worker` |
   | Root Directory | `backend` |
   | Config Path | `railway-cron.toml` |
   | Branch | `main` |

3. **Variables tab** — copy these from the existing `worker` service
   (the cron needs the same database + Resend secrets):

   - `DATABASE_URL`
   - `REDIS_URL` *(actually unused by this worker but the app loads
     it on startup; copy to avoid import-time crashes)*
   - `RESEND_API_KEY`
   - `RESEND_FROM_ADDRESS`
   - `DIGEST_DEFAULT_RECIPIENT`
   - `DIGEST_DASHBOARD_BASE_URL`
   - `ENVIRONMENT=production`

   Skip everything else (parcel-ingest endpoints, anthropic keys,
   etc — the digest worker never touches those).

4. **Settings → Deploy section** — confirm the `cronSchedule` field
   reads `0 12 * * *` (pulled from `railway-cron.toml`). This is
   12:00 UTC every day = 7am EST / 8am EDT.

5. **Click Deploy.** Railway will build the container, then hold it
   idle until the next 12:00 UTC tick.

## Verification (two steps)

### Step A: prove the service works without waiting for the schedule

Top-right of the cron service page in Railway → **"Run Now"**. This
fires the container immediately as if cron had triggered. Expected:

- Build logs show `pip install` completes
- Deploy logs show `eligible_filters: N`, then one
  `digest filter=... parcels=... resend_id=...` line per email sent,
  then container exits 0
- You receive emails for every filter where `daily_email_enabled =
  true` and `last_email_sent_at` is null or >23h old

If "Run Now" fails: read the build/deploy logs in Railway. The most
common failure is missing env vars (step 3). The second most common
is the 23h cooldown gate suppressing all emails — temporarily flip
the gate by setting `last_email_sent_at = NULL` on one filter via
SQL, then re-run.

### Step B: confirm the scheduled fire (next-day check)

Run this SQL in Supabase the morning after first deploy:

```sql
SELECT name, daily_email_enabled, last_email_sent_at
  FROM buybox_filters
 WHERE daily_email_enabled = true
 ORDER BY last_email_sent_at DESC;
```

`last_email_sent_at` should be within a few minutes of 12:00 UTC.
If it matches an hour you manually ran `_run-digest`, the schedule
didn't fire — check the Railway cron service's deploy history for
a missed run.

## Operating notes

**Why a separate service?** The web service auto-restarts on crash
(restartPolicy=ON_FAILURE). The cron must NOT — `restartPolicyType
= "NEVER"` in the config — because a failed digest run would
otherwise loop forever and re-email every recipient until the
cooldown caught up.

**Why 12:00 UTC?** It's 7am EST / 8am EDT — the operator's
inbox-check time. DST cutoffs shift the local hour by one, which is
acceptable for a digest email.

**Idempotency:** `run_once(force=False)` respects two cooldowns:
- `BuyboxFilter.last_email_sent_at < now() - 23h`
- Per parcel: `ParcelBuyboxScore.notified_at IS NULL`

A duplicate cron fire (Railway retry, schedule overlap) is a no-op.

**To temporarily disable the cron:** Railway service → Settings →
delete the `cronSchedule` value or set `restartPolicyType = NEVER`
+ "Disable Deployments". Do NOT just delete the service unless
you want to lose the variables config.

**To test schedule changes:** set cron to `*/15 * * * *` (every 15
min), wait for two fires, verify, then revert to `0 12 * * *`. The
23h cooldown means each test fire is idempotent — same emails won't
re-send within the day.

## Failure modes & what to do

| Symptom | Likely cause | Fix |
|---|---|---|
| Build fails on `pip install` | Backend dep added but `pyproject.toml` not committed | Re-deploy after pushing the dep |
| `RESEND_API_KEY is unset` log | Variables not copied to cron service | Copy from `worker` (step 3) |
| Email never arrives, no log line | `daily_email_enabled = false` on every filter | Toggle email-enabled on a filter via the dashboard |
| Email fires twice in a day | `last_email_sent_at` got reset by something | Check for accidental UPDATE; manually set it to now() to stop loop |
| Cron silently skipped | Railway sometimes drops a cron fire under heavy load (rare) | Check `last_email_sent_at` next day — if 48h gap, file a Railway support ticket |

## Future: when we add per-filter recipients

Sprint #5 in the roadmap adds `recipient_emails text[]` on
`buybox_filters`. The cron service config doesn't change — the
worker reads the field and sends to those recipients instead of
`DIGEST_DEFAULT_RECIPIENT`. No Railway-side change needed.
