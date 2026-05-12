# backend/uploads/

Operator-side audit copies of CoStar / LoopNet / Crexi exports. The Claude
skill on the operator's laptop writes here, then POSTs the file to the
Railway-hosted API. This folder is **not** the path the backend reads from —
the production app on Railway has its own ephemeral filesystem.

See [`docs/LISTINGS_INGESTION.md`](../../docs/LISTINGS_INGESTION.md) for the
full workflow + why we chose Plan A (skill-POSTs-API) over Plan B (cloud
storage poll).

`*.xlsx` and `*.csv` here are **gitignored** — they're operator data, not
source. Only this README is tracked.
