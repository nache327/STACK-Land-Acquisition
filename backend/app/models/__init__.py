"""
Import all models here so that SQLAlchemy metadata is fully populated
when Alembic generates migrations.
"""
from app.models.jurisdiction import CoverageLevel, Jurisdiction, ParcelSource  # noqa: F401
from app.models.parcel import Parcel  # noqa: F401
from app.models.zone_use_matrix import ZoneUseMatrix, UsePermission  # noqa: F401
from app.models.zoning_district import ZoneClass, ZoneSource, ZoningDistrict  # noqa: F401
from app.models.zoning_record import EnrichmentCache, ZoningOverlay, ZoningRule  # noqa: F401
from app.models.overlay import Overlay, OverlayType  # noqa: F401
from app.models.job import Job, JobStatus  # noqa: F401
from app.models.job_step import JobArtifact, JobStep  # noqa: F401
from app.models.shortlist import Shortlist  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.use_case import UseCase  # noqa: F401
from app.models.parcel_ring_metric import ParcelRingMetric  # noqa: F401
from app.models.buybox_filter import BuyboxFilter  # noqa: F401
from app.models.parcel_buybox_score import ParcelBuyboxScore  # noqa: F401
from app.models.coverage_snapshot import CoverageSnapshot  # noqa: F401
from app.models.zoning_source import ZoningSource  # noqa: F401
