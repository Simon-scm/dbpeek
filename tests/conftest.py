import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from typer.testing import CliRunner

from dbpeek.cli import app
from dbpeek.database import DatabaseContext, resolve_db_conn


@pytest.fixture
def run_cli(monkeypatch):
    monkeypatch.delenv("DBPEEK_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(app, list(args), env={"COLUMNS": "200"})

    return invoke


@pytest.fixture
def db(monkeypatch):
    database = resolve_db_conn("sqlite://")
    try:
        sql = Path(__file__).with_name("fixtures") / "edge_cases.sql"
        with database.engine.begin() as connection:
            connection.connection.driver_connection.executescript(sql.read_text(encoding="utf-8"))
        monkeypatch.setattr("dbpeek.cli.resolve_db_conn", lambda url: database)
        yield database
    finally:
        database.engine.dispose()


@pytest.fixture
def cross_schema_catalog(db, monkeypatch):
    get_foreign_keys = db.inspector.get_foreign_keys

    def get_cross_schema_keys(table_name, schema=None):
        keys = get_foreign_keys(table_name, schema=schema)
        if (schema, table_name) == ("main", "submissions"):
            return [dict(key, referred_schema="archive") for key in keys]
        return keys

    monkeypatch.setattr(db.inspector, "get_foreign_keys", get_cross_schema_keys)


@pytest.fixture
def postgres_graph(monkeypatch):
    dsn = os.getenv("DBPEEK_TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip("Set DBPEEK_TEST_POSTGRES_URL to run PostgreSQL integration tests")
    url = make_url(dsn)
    if url.get_backend_name() != "postgresql":
        pytest.fail("DBPEEK_TEST_POSTGRES_URL must identify a PostgreSQL test database")

    suffix = uuid4().hex[:12]
    sales = f"dbpeek_sales_{suffix}"
    crm = f"dbpeek_crm_{suffix}"
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET LOCAL search_path TO pg_catalog")
                connection.exec_driver_sql(f"CREATE SCHEMA {sales}")
                connection.exec_driver_sql(f"CREATE SCHEMA {crm}")
                for schema in (sales, crm):
                    connection.exec_driver_sql(f"CREATE TABLE {schema}.users (id INTEGER PRIMARY KEY)")
                connection.exec_driver_sql(
                    f"CREATE TABLE {sales}.orders (user_id INTEGER REFERENCES {crm}.users(id))"
                )
                db = DatabaseContext(engine, inspect(connection))
                monkeypatch.setattr("dbpeek.cli.resolve_db_conn", lambda url: db)
                yield sales, crm
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
