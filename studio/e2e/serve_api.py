"""Backend for the end-to-end test: a fresh database `studio_e2e` and its own export directory, on port 8712.

The test never touches the development database or `studio/exports/`.
    backend/.venv/Scripts/python e2e/serve_api.py
"""

import os
import pathlib
import shutil

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

STUDIO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = STUDIO / "backend"
OUT = pathlib.Path(__file__).resolve().parent / ".out"
ADMIN_URL = os.environ.get("STUDIO_ADMIN_URL", "postgresql+psycopg://studio:studio@localhost:5433/postgres")
URL = ADMIN_URL.rsplit("/", 1)[0] + "/studio_e2e"


def main() -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS studio_e2e WITH (FORCE)"))
        c.execute(text("CREATE DATABASE studio_e2e"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["url"] = URL
    command.upgrade(cfg, "head")
    shutil.rmtree(OUT, ignore_errors=True)
    os.environ["STUDIO_DATABASE_URL"] = URL
    os.environ["STUDIO_EXPORT_ROOT"] = str(OUT / "exports")
    uvicorn.run("studio_backend.main:app", host="127.0.0.1", port=8712, log_level="warning")


if __name__ == "__main__":
    main()
