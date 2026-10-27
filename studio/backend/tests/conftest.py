import os
import pathlib

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = pathlib.Path(__file__).resolve().parents[3]          # the voxstage repository
DOMAINS = ROOT / "domains"
BACKEND = pathlib.Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("STUDIO_ADMIN_URL", "postgresql+psycopg://studio:studio@localhost:5433/postgres")
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/studio_test"


@pytest.fixture(scope="session")
def db_url():
    """A fresh database built by the Alembic migrations (so the migrations are tested too)."""
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS studio_test WITH (FORCE)"))
        c.execute(text("CREATE DATABASE studio_test"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["url"] = TEST_URL
    command.upgrade(cfg, "head")
    os.environ["STUDIO_DATABASE_URL"] = TEST_URL
    from studio_backend import db
    db.reset_engine()
    return TEST_URL


@pytest.fixture()
def session(db_url):
    from studio_backend import db
    from studio_backend.models import Base
    engine = db.engine()
    with engine.begin() as c:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    with db.session_scope() as s:
        yield s
