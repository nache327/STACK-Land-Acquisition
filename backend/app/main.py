from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import (
    jobs,
    jurisdictions,
    ordinances,
    parcels,
    pdf_parser,
    shortlist,
    zoning_districts,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to do (Alembic handles migrations)
    yield
    # Shutdown: dispose engine
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

app.include_router(jobs.router, prefix="/api")
app.include_router(jurisdictions.router, prefix="/api")
app.include_router(ordinances.router, prefix="/api")
app.include_router(parcels.router, prefix="/api")
app.include_router(pdf_parser.router, prefix="/api")
app.include_router(shortlist.router, prefix="/api")
app.include_router(zoning_districts.router, prefix="/api")


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/api/openapi.json", include_in_schema=False)
async def custom_openapi():
    return app.openapi()
