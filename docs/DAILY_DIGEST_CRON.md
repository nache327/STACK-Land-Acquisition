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

**The exit code is a pager, not a log level.** Each tick of a
`restartPolicyType = NEVER` service is a one-shot *deployment*, and
Railway emails the account owner "Deploy Crashed!" on ANY nonzero
exit. At one tick per 10 minutes that is 144 emails a day, forever,
for any condition that does not clear on its own.

So `queued_job_watchdog.main()` exits **0** for every sub-task
outcome and records the four codes in `ops_cron_heartbeat` instead.
It exits nonzero for exactly one thing: it could not write that
heartbeat row — a tick that ran blind, which is the only state the
DB cannot tell you about afterwards. Nothing in `railway-cron.toml`
may re-raise a sub-task code through the shell.

This was learned the hard way (2026-10-09). One job queued
2026-08-10 that no worker ever claimed — `recover_stale_jobs` only
rescues rows with a non-NULL `locked_at`, so nothing could ever
close it — made the watchdog report "stuck job" and exit 1 on every
tick for two months. Clear orphans with
`python scripts/expire_orphaned_queued_jobs.py` (dry-run by
default).

**Is the cron actually alive?** Ask the DB, not Railway:

```sql
SELECT ran_at, watchdog_code, refresh_code, digest_code, sentinel_code, host
  FROM ops_cron_heartbeat ORDER BY ran_at DESC LIMIT 10;
```

A gap means the cron did not run. A row with a nonzero column means
that sub-task failed while the tick itself was healthy.

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
| Flood of "Deploy Crashed!" emails | Something made the tick exit nonzero — most likely a permanent condition that cannot self-clear | Read the newest `ops_cron_heartbeat` row to see which sub-task. An empty table means the tick never got far enough to write one |
| `ops_cron_heartbeat` empty / stale | The cron is not running this code at all (stale image), or cannot reach the DB | Redeploy the cron service; confirm its `DATABASE_URL` matches the web service's |
| Watchdog reports a stuck job that never clears | Job was queued but never claimed, so `locked_at IS NULL` and `recover_stale_jobs` cannot see it | `python scripts/expire_orphaned_queued_jobs.py --apply` |

## Future: when we add per-filter recipients

Sprint #5 in the roadmap adds `recipient_emails text[]` on
`buybox_filters`. The cron service config doesn't change — the
worker reads the field and sends to those recipients instead of
`DIGEST_DEFAULT_RECIPIENT`. No Railway-side change needed.
