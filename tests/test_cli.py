import sqlite3
from contextlib import closing

import pytest
from sqlalchemy import event
from typer.testing import CliRunner

from dbpeek.cli import app
from dbpeek.database import ResolvedRef, resolve_db_conn


@pytest.fixture
def database_url(tmp_path):
    path = tmp_path / "example.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
            INSERT INTO users (name) VALUES ('Alice'), ('Bob');
            CREATE TABLE submissions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER REFERENCES users(id)
            );
            CREATE TABLE parent (a INTEGER, b INTEGER, PRIMARY KEY (a, b));
            CREATE TABLE child (
                x INTEGER,
                y INTEGER,
                CONSTRAINT parent_key FOREIGN KEY (x, y) REFERENCES parent (a, b)
            );
            CREATE VIEW preview AS
            SELECT '[red]Alice[/red]' AS "[blue]name[/blue]";
            """
        )
    return f"sqlite:///{path.as_posix()}"


@pytest.mark.parametrize(
    ("table_name", "expected_rows"), [("users", 2), ("main.submissions", 0)]
)
def test_count_reports_rows(database_url, table_name, expected_rows):
    result = CliRunner().invoke(app, ["--url", database_url, "count", table_name])

    assert result.exit_code == 0, result.output
    assert f"Rows: {expected_rows}" in result.output.splitlines()
    assert "Columns: 2" in result.output.splitlines()


def test_fks_for_table_with_foreign_key(database_url):
    result = CliRunner().invoke(app, ["--url", database_url, "fks", "main.submissions"])

    assert result.exit_code == 0, result.output
    assert "user_id -> main.users.id" in result.output
    assert "main.users" not in result.output.splitlines()


def test_fks_for_table_without_foreign_keys(database_url):
    result = CliRunner().invoke(app, ["--url", database_url, "fks", "users"])

    assert result.exit_code == 0, result.output
    assert "main.users" in result.output.splitlines()
    assert "null" in result.output
    assert "main.submissions" not in result.output


@pytest.mark.parametrize("schema_flag, target", [([], "main.parent"), (["--shownoschema"], "parent")])
def test_fks_keeps_composite_column_pairs_together(database_url, schema_flag, target):
    result = CliRunner().invoke(app, ["--url", database_url, "fks", "child", *schema_flag])

    assert result.exit_code == 0, result.output
    assert f"x -> {target}.a, y -> {target}.b (name: parent_key)" in result.output


@pytest.mark.parametrize("row_count, expected_rows", [(0, 0), (1, 1), (None, 2)])
def test_get_rows_applies_limit_in_sql(database_url, row_count, expected_rows):
    db = resolve_db_conn(database_url)
    statements = []

    @event.listens_for(db.engine, "before_cursor_execute")
    def record_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        columns, *rows = db.get_rows(ResolvedRef(name="users", schema_name="main"), row_count)
    finally:
        db.engine.dispose()

    assert columns == ["id", "name"]
    assert len(rows) == expected_rows
    query = next(sql for sql in statements if "FROM main.users" in sql)
    assert ("LIMIT" in query.upper()) is (row_count is not None)


def test_rows_preserves_markup_in_view_headers_and_values(database_url):
    result = CliRunner().invoke(app, ["--url", database_url, "rows", "preview"])

    assert result.exit_code == 0, result.output
    assert "[blue]name[/blue]" in result.output
    assert "[red]Alice[/red]" in result.output


@pytest.mark.parametrize("command", ["rows", "count"])
@pytest.mark.parametrize("args", [("users", "--schema", "missing"), ("missing.users",)])
def test_relation_commands_report_missing_schema(database_url, command, args):
    result = CliRunner().invoke(app, ["--url", database_url, command, *args])

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert result.stderr.strip() == "Schema 'missing' not found."
