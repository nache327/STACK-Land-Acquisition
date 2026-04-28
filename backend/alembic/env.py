from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import Base + all models so metadata is fully populated
from app.config import settings
from app.db import Base
import app.models  # noqa: F401 — triggers all model imports

# Alembic Config object
config = context.config

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Resolve the sync DB URL from app.config (which loads .env consistently
    with the API + worker), so all three components target the same database.
    """
    print(
        f"[alembic] using database={settings.database_url_sanitized} "
        f"environment={settings.environment}"
    )
    return settings.sync_database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
