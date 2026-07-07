FROM python:3.12-slim

# System dependencies for GDAL / GeoPandas / PostGIS client.
# Chromium runtime deps live in their own apt layer below so a Playwright
# install failure can't invalidate the GIS toolchain layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    gdal-bin \
    libgeos-dev \
    libproj-dev \
    libpq-dev \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Chromium runtime deps — separate apt layer to bound peak build memory.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache).
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Playwright browser binaries in a separate layer so their ~150MB extract
# doesn't compound peak memory with pip's resolver.
RUN playwright install chromium

# Copy application source
COPY . .

EXPOSE 8000

# Run alembic migrations once at boot, then hand off to honcho so BOTH the web
# (uvicorn) AND worker (dramatiq) processes are supervised. honcho exits with a
# non-zero code as soon as ANY supervised process dies — Railway will then
# restart the container instead of silently running with only one half up. The
# previous `cmd1 & cmd2` pattern hid a 58-hour dramatiq outage (see STATUS.md:
# "Critical Deployment Drift Incident") because the foreground uvicorn kept
# the container "healthy" while the backgrounded dramatiq had never launched.
#
# MIGRATION CONTRACT (2026-07-06 outage, ~25 min of 502s): the REAL migration
# runner is Railway's pre-deploy command (`alembic upgrade head`, see
# railway.toml) which runs BEFORE the traffic swap — a failing/slow migration
# aborts the rollout while the old container keeps serving. The boot-time
# alembic below is kept only as a no-op safety net for environments without
# the pre-deploy step; by the time this CMD runs on Railway, the DB is
# already at head and it completes in ~2s. Do NOT put heavy migrations on
# this path — follow the authoring rules in alembic/versions/0042_*.py.
CMD ["sh", "-c", "alembic upgrade head && exec honcho start --no-colour"]
