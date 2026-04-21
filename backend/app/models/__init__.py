"""
Import all models here so that SQLAlchemy metadata is fully populated
when Alembic generates migrations.
"""
from app.models.jurisdiction import CoverageLevel, Jurisdiction, ParcelSource  # noqa: F401
from app.models.parcel import Parcel  # noqa: F401
from app.models.zone_use_matrix import ZoneUseMatrix, UsePermission  # noqa: F401
from app.models.zoning_district import ZoneClass, ZoneSource, ZoningDistrict  # noqa: F401
from app.models.overlay import Overlay, OverlayType  # noqa: F401
from app.models.job import Job, JobStatus  # noqa: F401
from app.models.shortlist import Shortlist  # noqa: F401
