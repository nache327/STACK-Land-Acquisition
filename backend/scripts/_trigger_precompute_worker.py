"""Enqueue a ring-metrics precompute to the Dramatiq WORKER path (sturdy long-job mode).

WHY: the public endpoint POST /jurisdictions/{id}/_precompute-ring-metrics runs the job
in a FastAPI BackgroundTask on the WEB dyno. For county-sized jurisdictions (250k+
parcels, 60+ min) that mode is fragile — a web dyno restart/deploy silently kills the
task, leaving the Redis job-state orphaned at status="running" forever (observed on
Bergen 2026-06-11: tracts 195/195 at +2min, then parcels_written=0 for 65+ min). The
worker path runs under the Dramatiq worker service, which is built for long jobs and
survives web-dyno churn.

WHERE TO RUN: on Railway (the worker or app service shell) — NOT locally. It needs the
Dramatiq broker (Redis) connection, which lives only in the Railway env. Locally there
are no broker creds, so `.send()` has nowhere to go.

USAGE (Railway shell, from backend/):
    python scripts/_trigger_precompute_worker.py <jurisdiction_id>
e.g.
    python scripts/_trigger_precompute_worker.py 4bf00234-4455-4987-a067-b22ee6b6aa1f   # Bergen
    python scripts/_trigger_precompute_worker.py 394ef40c-ca0d-4d57-9b11-dc5417430240   # Somerset
    python scripts/_trigger_precompute_worker.py 746b7604-f362-470f-aa42-70dc8973b4ee   # Morris

The worker actor (process_ring_metrics_precompute in app/services/job_queue.py) runs the
precompute AND auto-re-scores the default filter afterward. It does NOT write a Redis
job-state row (that's only the web endpoint), so monitor via the parcel_ring_metrics row
count climbing for the jurisdiction, or the worker-service logs.
"""
import sys
import uuid


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/_trigger_precompute_worker.py <jurisdiction_id>")
    jid = uuid.UUID(sys.argv[1])
    # Import here so the broker is configured from the Railway env at call time.
    from app.services.job_queue import enqueue_ring_metrics_precompute
    enqueue_ring_metrics_precompute(jid)
    print(f"enqueued ring_metrics_precompute for jurisdiction {jid} to the Dramatiq worker path")


if __name__ == "__main__":
    main()
