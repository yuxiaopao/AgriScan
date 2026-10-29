"""Use the application's connection, including its in-memory test database."""
from alembic import context

from app.db import Base, make_database
from app import admin_models, assistant, detection_assistant, extensions  # Register all metadata.
from app import runtime_config  # Register persisted runtime settings for metadata inspection.


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata,
                      compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    from app.config import Settings
    engine, _ = make_database(Settings().database_url)
    try:
        with engine.begin() as connection:
            run(connection)
    finally:
        engine.dispose()
