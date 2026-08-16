from logging.config import fileConfig
import os
import sys
import logging

from sqlalchemy import create_engine
from sqlalchemy import pool
from dotenv import load_dotenv

from alembic import context

# Load environment variables
load_dotenv()

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import our models and database configuration
from app.models import Base

# Get DATABASE_URL with Heroku compatibility fix
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print(f"Fixed DATABASE_URL for SQLAlchemy compatibility")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Set the database URL from environment variable
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Configure logging for migrations
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
logger = logging.getLogger("alembic")
logger.info(f"Running migrations in {ENVIRONMENT} environment")
logger.info(f"Database URL (masked): {DATABASE_URL.split('@')[0] + '@***' if '@' in DATABASE_URL else 'sqlite'}")

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


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
    # engine_from_config only accepts string-valued config options (it's built
    # for ini-file parsing), so connect_args must be passed directly to
    # create_engine as a real dict rather than embedded as a JSON string in
    # the config mapping - passing it via engine_from_config raises
    # "dictionary update sequence element #0 has length 1; 2 is required"
    # because it tries to iterate the JSON string as key/value pairs.
    engine_kwargs = {"poolclass": pool.NullPool}

    if ENVIRONMENT == "production":
        engine_kwargs.update({
            "pool_pre_ping": True,
            "pool_recycle": 1800,  # 30 minutes
            "connect_args": {"sslmode": "require", "connect_timeout": 30},
        })
        logger.info("Using production database configuration")

    url = config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url, **engine_kwargs)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            compare_type=True,  # Compare column types
            compare_server_default=True,  # Compare server defaults
            render_as_batch=True,  # Enable batch operations for SQLite compatibility
        )

        with context.begin_transaction():
            try:
                logger.info("Starting database migration")
                context.run_migrations()
                logger.info("Database migration completed successfully")
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
