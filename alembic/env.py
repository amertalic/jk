from logging.config import fileConfig
import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# add project root to sys.path so `models` can be imported
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from settings import settings
from models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from project settings (best practice)
if not getattr(settings, "ALCHEMY_DB_URL", None):
    raise RuntimeError(
        "ALCHEMY_DB_URL is not set in settings; please configure your .env or environment variables"
    )

config.set_main_option("sqlalchemy.url", settings.ALCHEMY_DB_URL)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.begin() as connection:
        # Check if a custom search_path was set (for multi-schema support)
        search_path = config.get_main_option("search_path")
        if search_path:
            connection.execute(text(f'SET search_path TO "{search_path}", public'))

        # Get version_table_schema if set (for per-schema alembic_version tracking)
        version_table_schema = config.get_main_option("version_table_schema")

        # Configure context with schema-specific version table if specified
        context_config = {
            "connection": connection,
            "target_metadata": target_metadata,
        }

        if version_table_schema:
            context_config["version_table_schema"] = version_table_schema

        context.configure(**context_config)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
