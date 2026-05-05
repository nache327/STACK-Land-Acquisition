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

CMD ["sh", "-c", "alembic upgrade head && dramatiq app.worker --processes 2 --threads 2 & uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
