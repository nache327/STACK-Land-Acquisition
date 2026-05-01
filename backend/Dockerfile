FROM python:3.12-slim

# Install system dependencies for GDAL / GeoPandas / PostGIS client
# and Playwright Chromium browser runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    gdal-bin \
    libgeos-dev \
    libproj-dev \
    libpq-dev \
    gcc \
    g++ \
    curl \
    # Chromium runtime deps (required by Playwright)
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

# Install Python deps first (layer cache)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . && playwright install chromium

# Copy application source
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && dramatiq app.worker --processes 2 --threads 2 & uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
