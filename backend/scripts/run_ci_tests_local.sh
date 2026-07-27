#!/usr/bin/env bash
# Run the FULL backend suite locally, EQUIVALENT TO CI ON BOTH AXES:
#   * database    — the same postgis/postgis:16-3.4 image, so the ~63
#                   DB-dependent tests actually run instead of erroring
#   * interpreter — Python 3.12 in a container, because CI is 3.12 and dev
#                   machines here are 3.13
#
# WHY BOTH. Plain `pytest` in backend/ reports something like "833 passed, 63
# errors". Those errors are NOT noise — they are DB tests that run in CI, so a
# third of the suite was a local blind spot. But fixing only the database half
# leaves a second, subtler trap: pytest still running on local 3.13 while CI runs
# 3.12, so a version-specific failure passes locally and still reds the PR. This
# script closes both.
#
# USAGE (from anywhere):
#   backend/scripts/run_ci_tests_local.sh                  # full suite, like CI
#   backend/scripts/run_ci_tests_local.sh -k municipality   # extra pytest args
#   backend/scripts/run_ci_tests_local.sh --rebuild        # rebuild the 3.12 image
#   backend/scripts/run_ci_tests_local.sh --down           # remove containers/network
#   HOST_PYTHON=1 backend/scripts/run_ci_tests_local.sh    # escape hatch: host
#                                                          # interpreter (NOT
#                                                          # CI-equivalent)
#
# Requires Docker Desktop running. On Windows use Git Bash. If the daemon is
# unreachable, check that the `com.docker.service` backend service is started —
# Docker Desktop's UI can be up while the service is stopped, and starting it
# needs administrator rights.
set -euo pipefail

NET=parcellogic-ci-net
DB_CONTAINER=parcellogic-ci-postgres
DB_IMAGE=postgis/postgis:16-3.4
TEST_IMAGE=parcellogic-citest:py312
PGDB=zoning_test
PGPORT="${PGPORT:-5432}"     # host port, for poking at the DB yourself
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == "--down" ]]; then
  docker rm -f "$DB_CONTAINER" >/dev/null 2>&1 && echo "removed $DB_CONTAINER" || true
  docker network rm "$NET" >/dev/null 2>&1 && echo "removed network $NET" || true
  exit 0
fi

REBUILD=0
if [[ "${1:-}" == "--rebuild" ]]; then REBUILD=1; shift; fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon unreachable. Start Docker Desktop (and its" >&2
  echo "       com.docker.service backend service — needs admin) and retry." >&2
  exit 1
fi

# PREFLIGHT: free disk. Learned the hard way 2026-07-27 — with ~96MB free the
# build died at "exporting layers" with
#   blob sha256:… expected at …/content/blobs/sha256/…: input/output error
# i.e. a TRUNCATED write to containerd's content store, reported as corruption
# with no mention of disk. Worse, the store STAYS corrupt afterwards (`docker
# images` then fails too), so a silent disk-full turns into a broken daemon.
# Fail loudly and early instead. ~3GB covers slim + GDAL + deps + chromium.
_MIN_FREE_MB=4096
_free_mb="$(df -Pm /var/tmp 2>/dev/null | awk 'NR==2{print $4}')"
[ -z "${_free_mb:-}" ] && _free_mb="$(df -Pm . 2>/dev/null | awk 'NR==2{print $4}')"
if [ -n "${_free_mb:-}" ] && [ "$_free_mb" -lt "$_MIN_FREE_MB" ]; then
  echo "ERROR: only ${_free_mb}MB free; need ~${_MIN_FREE_MB}MB to build $TEST_IMAGE." >&2
  echo "       Building anyway corrupts Docker's content store rather than" >&2
  echo "       failing cleanly. Free space first, then retry." >&2
  echo "       If the store is ALREADY corrupt (docker images errors with" >&2
  echo "       'input/output error'), use Docker Desktop > Troubleshoot >" >&2
  echo "       'Clean / Purge data' — that both reclaims the disk and rebuilds" >&2
  echo "       the store. This script recreates the containers it needs." >&2
  exit 1
fi

docker network create "$NET" >/dev/null 2>&1 || true

# ── database, on the shared network so the test container can reach it by name ──
if ! docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
  docker rm -f "$DB_CONTAINER" >/dev/null 2>&1 || true
  echo "starting $DB_IMAGE ..."
  docker run -d --name "$DB_CONTAINER" --network "$NET" \
    -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB="$PGDB" \
    -p "${PGPORT}:5432" "$DB_IMAGE" >/dev/null
  printf "waiting for postgres"
  for _ in $(seq 1 60); do
    if docker exec "$DB_CONTAINER" pg_isready -U postgres -d "$PGDB" >/dev/null 2>&1; then
      echo " ready"; break
    fi
    printf "."; sleep 2
  done
  docker exec "$DB_CONTAINER" pg_isready -U postgres -d "$PGDB" >/dev/null 2>&1 || {
    echo " FAILED"; docker logs --tail 30 "$DB_CONTAINER"; exit 1; }
else
  echo "reusing running $DB_CONTAINER (--down to reset)"
fi

# ── escape hatch: host interpreter. Explicitly NOT CI-equivalent. ──
if [[ "${HOST_PYTHON:-0}" == "1" ]]; then
  echo "WARNING: running on the HOST interpreter ($(python -V 2>&1)); CI uses 3.12."
  echo "         A version-specific failure will NOT be caught. Prefer the default."
  cd "$BACKEND_DIR"
  DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:${PGPORT}/${PGDB}" \
  ANTHROPIC_API_KEY="" REGRID_API_KEY="" REDIS_URL="redis://localhost:6379" \
    python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=25 \
                     -m "not integration" "$@"
  exit $?
fi

# ── CI-equivalent interpreter (3.12, containerised) ──
if [[ "$REBUILD" == "1" ]] || ! docker image inspect "$TEST_IMAGE" >/dev/null 2>&1; then
  echo "building $TEST_IMAGE (first run installs GDAL + deps + chromium; several minutes)"
  docker build -f "$BACKEND_DIR/Dockerfile.citest" -t "$TEST_IMAGE" "$BACKEND_DIR"
fi

echo "running the CI suite under Python 3.12 (same flags as .github/workflows/ci.yml)"
# SAFETY: the DSN names the DB CONTAINER, unreachable from outside this network,
# so the destructive fixtures (drop_all/create_all) cannot touch prod even if
# backend/.env is present in the mount. conftest additionally refuses a
# Supabase/pooled DSN; env vars beat .env in pydantic-settings.
docker run --rm --network "$NET" \
  -v "$BACKEND_DIR:/app" \
  -e DATABASE_URL="postgresql+asyncpg://postgres:postgres@${DB_CONTAINER}:5432/${PGDB}" \
  -e ANTHROPIC_API_KEY="" \
  -e REGRID_API_KEY="" \
  -e REDIS_URL="redis://localhost:6379" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$TEST_IMAGE" \
    --cov=app --cov-report=term-missing --cov-fail-under=25 \
    -m "not integration" "$@"
