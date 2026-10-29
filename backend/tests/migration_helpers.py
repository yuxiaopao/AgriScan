"""Create an exact old schema through its recorded migrations, never live files."""
from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_to_revision(engine,revision):
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/'alembic.ini'))
    config.set_main_option('script_location',str(root/'alembic'))
    with engine.begin() as connection:
        config.attributes['connection']=connection
        command.upgrade(config,revision)
