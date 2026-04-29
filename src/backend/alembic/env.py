from logging.config import fileConfig

from sqlalchemy import pool
from alembic import context

from app.core.config import settings
from app.db.base import Base

# Import all models so that Base.metadata includes them for autogenerate
import app.modules.identity.models  # noqa: F401
import app.modules.inventory.models  # noqa: F401
import app.modules.booking.models  # noqa: F401
import app.modules.crm.models  # noqa: F401
import app.modules.fulfillment.models  # noqa: F401
import app.modules.expediente.models  # noqa: F401
import app.modules.finance.models  # noqa: F401
import app.modules.access.models  # noqa: F401
import app.modules.audit.models
import app.modules.uma_rates.models
import app.modules.notifications.models
import app.modules.catalog.models
import app.modules.pricing.models
import app.modules.discounts.models
import app.modules.reservation_documents.models


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
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
    """Run migrations in 'online' mode."""
    connectable = context.config.attributes.get("connection", None)
    if connectable is None:
        from sqlalchemy import create_engine
        connectable = create_engine(
            config.get_main_option("sqlalchemy.url"),
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
