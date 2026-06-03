import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.version import get_pipeline_version
from app.api import (
    admin_backfill,
    admin_op5,
    buybox,
    census_proxy,
    competition,
    debug,
    jobs,
    jurisdictions,
    listings,
    ordinances,
    parcels,
    pdf_parser,
    shortlist,
    zoning_districts,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

PIPELINE_VERSION = get_pipeline_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PIPELINE_VERSION=%s", PIPELINE_VERSION)
    logger.info(
        "API boot — environment=%s database=%s redis=%s",
        settings.environment,
        settings.database_url_sanitized,
        settings.redis_url_sanitized,
    )
    from app.services.job_watchdog import recover_stale_jobs

    async def _watchdog_loop() -> None:
        while True:
            await asyncio.sleep(5 * 60)
            try:
                recovered = await recover_stale_jobs()
                if recovered:
                    logger.info("Periodic watchdog: recovered %d stale locked jobs", recovered)
            except Exception:
                logger.exception("Periodic watchdog iteration failed")

    try:
        recovered = await recover_stale_jobs()
        if recovered:
            logger.info("Startup watchdog: recovered %d stale locked jobs", recovered)
    except Exception:
        logger.exception("Startup watchdog failed — continuing boot")

    watchdog_task = asyncio.create_task(_watchdog_loop())
    yield
    watchdog_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        pass
    from app.db import engine
    await engine.dispose()


app = FastAPI(
    title="Zoning Finder API",
    description=(
        "Find vacant parcels zoned for self-storage, mini-warehouse, "
        "light industrial, or luxury garage condominium development."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(competition.router, prefix="/api")
app.include_router(debug.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(jurisdictions.router, prefix="/api")
app.include_router(ordinances.router, prefix="/api")
app.include_router(parcels.router, prefix="/api")
app.include_router(pdf_parser.router, prefix="/api")
app.include_router(shortlist.router, prefix="/api")
app.include_router(zoning_districts.router, prefix="/api")
app.include_router(buybox.router, prefix="/api")
app.include_router(census_proxy.router, prefix="/api")
app.include_router(listings.router, prefix="/api")
app.include_router(admin_backfill.router, prefix="/api")
app.include_router(admin_op5.router, prefix="/api")


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {
        "status": "ok",
        "version": app.version,
        "pipeline_version": PIPELINE_VERSION,
    }


@app.get("/api/openapi.json", include_in_schema=False)
async def custom_openapi():
    return app.openapi()
