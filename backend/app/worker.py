"""Dramatiq worker module.

Run with:
    dramatiq app.worker
"""
import logging

from app.config import settings
from app.version import get_pipeline_version
from app.services import job_queue as job_queue  # noqa: F401 — registers actors + broker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

logger.info("PIPELINE_VERSION=%s", get_pipeline_version())
logger.info(
    "Worker boot — environment=%s database=%s redis=%s",
    settings.environment,
    settings.database_url_sanitized,
    settings.redis_url_sanitized,
)
