import ast
import json
import sqlite3
from contextlib import closing

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

def assert_ok(result):
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stderr == ""
    return result.stdout


def assert_error(result, message, *, code=1):
    assert result.exit_code == code, (result.output, result.exception)
    assert result.stdout == ""
    assert message in result.stderr


def test_default_command_prints_database_metadata(db, run_cli):
    info = json.loads(assert_ok(run_cli()))
    assert info["dbms"] == "sqlite"
    assert info["driver"] == "pysqlite"


def test_schemas_includes_empty_schema(db, run_cli):
    output = assert_ok(run_cli("schemas"))
    assert set(ast.literal_eval(output)) == {"main", "archive", "cycles", "empty"}


@pytest.mark.parametrize(
    "command, expected",
    [
        ("tables", {"main.users", "archive.users", "archive.preview", "cycles.cycle_a"}),
        ("views", {"main.preview", "main.empty_preview"}),
    ],
)
def test_lists_relations_across_schemas(db, run_cli, command, expected):
    relations = set(ast.literal_eval(assert_ok(run_cli(command))))
    assert expected <= relations
    if command == "views":
        assert relations == expected
    else:
        assert "main.preview" not in relations


@pytest.mark.parametrize("command", ["tables", "views"])
def test_lists_existing_empty_schema(db, run_cli, command):
    assert ast.literal_eval(assert_ok(run_cli(command, "--schema", "empty"))) == []


def test_tables_can_filter_and_hide_schema(db, run_cli):
    output = assert_ok(run_cli("tables", "--schema", "archive", "--shownoschema"))
    assert set(ast.literal_eval(output)) == {"only_archive", "preview", "users"}


def test_info_for_one_table_outputs_json(db, run_cli):
    output = json.loads(assert_ok(run_cli("info", "main.users")))
    assert output["schema_name"] == "main"
    assert output["pk"]["constrained_columns"] == ["id"]
    assert output["columns"][1]["default"] == "'[red]Bob[/red]'"


def test_info_for_matching_tables_outputs_one_json_array(db, run_cli):
    output = json.loads(assert_ok(run_cli("info", "users")))
    tables = {table["schema_name"]: table for table in output}
    assert set(tables) == {"main", "archive"}
    assert [column["name"] for column in tables["archive"]["columns"]] == [
        "id", "archived_name",
    ]


@pytest.mark.parametrize("command", ["info", "fks"])
def test_missing_explicit_table_is_an_error(db, run_cli, command):
    assert_error(run_cli(command, "missing"), "Provided table does not exist")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="info omits UNIQUE and CHECK")
def test_info_includes_declared_unique_and_check_constraints(db, run_cli):
    output = assert_ok(run_cli("info", "main.users"))
    assert "users_name_unique" in output
    assert "users_name_check" in output


def test_fks_shows_qualified_target_for_simple_foreign_key(db, run_cli):
    output = assert_ok(run_cli("fks", "main.submissions"))
    assert "user_id -> main.users.id" in output
    assert "main.users" not in output.splitlines()


def test_fks_accepts_existing_empty_schema(db, run_cli):
    assert assert_ok(run_cli("fks", "--schema", "empty")) == ""


def test_fks_without_keys_displays_both_matching_tables(db, run_cli):
    output = assert_ok(run_cli("fks", "users"))
    assert {"main.users", "archive.users"} <= set(output.splitlines())
    assert output.count("null") == 2


@pytest.mark.parametrize("table, name", [("child", "parent_key"), ("implicit_child", "None")])
@pytest.mark.parametrize("hide_schema", [False, True])
def test_fks_preserves_composite_column_order(db, run_cli, table, name, hide_schema):
    flags = ("--shownoschema",) if hide_schema else ()
    target = "parent" if hide_schema else "main.parent"
    output = assert_ok(run_cli("fks", table, *flags))
    assert f"x -> {target}.a, y -> {target}.b (name: {name})" in output


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fks crashes on missing target columns")
def test_fks_keeps_unresolved_targets_visible(db, run_cli):
    output = assert_ok(run_cli("fks", "main.orphan"))
    assert "parent_id" in output
    assert "missing_parent" in output


def test_fks_formats_a_cross_schema_target_from_inspector(cross_schema_catalog, run_cli):
    output = assert_ok(run_cli("fks", "main.submissions"))
    assert "user_id -> archive.users.id" in output
    assert "user_id -> main.users.id" not in output


@pytest.mark.parametrize(
    "name, expected_rows, expected_columns, label",
    [
        ("main.users", 2, 2, "Table: main.users"),
        ("archive.users", 1, 2, "Table: archive.users"),
        ("submissions", 0, 2, "Table: main.submissions"),
        ("main.preview", 1, 1, "View: main.preview"),
        ("empty_preview", 0, 2, "View: main.empty_preview"),
        ("only_archive", 1, 1, "Table: archive.only_archive"),
    ],
)
def test_count_resolves_and_counts_the_requested_object(
    db, run_cli, name, expected_rows, expected_columns, label
):
    output = assert_ok(run_cli("count", name))
    assert {label, f"Rows: {expected_rows}", f"Columns: {expected_columns}"} <= set(
        output.splitlines()
    )


@pytest.mark.parametrize("command", ["rows", "count"])
@pytest.mark.parametrize("name", ["users", "preview"])
def test_single_object_commands_report_ambiguity(db, run_cli, command, name):
    result = run_cli(command, name)
    assert_error(result, "Please specify a schema")
    assert f"main.{name}" in result.stderr
    assert f"archive.{name}" in result.stderr


@pytest.mark.parametrize("command", ["rows", "count"])
@pytest.mark.parametrize("args", [("users", "--schema", "missing"), ("missing.users",)])
def test_single_object_commands_report_missing_schema(db, run_cli, command, args):
    assert_error(run_cli(command, *args), "Schema 'missing' not found.")


@pytest.mark.parametrize("command", ["rows", "count"])
def test_single_object_commands_report_missing_relation(db, run_cli, command):
    assert_error(run_cli(command, "does_not_exist"), "Table or View 'does_not_exist' not found.")


def test_rows_uses_explicit_schema_for_data_and_title(db, run_cli):
    output = assert_ok(run_cli("rows", "users", "--schema", "archive"))
    assert "archive.users" in output
    assert "ArchiveOnly" in output
    assert "Alice" not in output


def test_rows_preserves_markup_in_view_headers_and_values(db, run_cli):
    output = assert_ok(run_cli("rows", "main.preview"))
    assert "[blue]name[/blue]" in output
    assert "[red]Bob[/red]" in output


@pytest.mark.parametrize("name", ["submissions", "empty_preview"])
def test_rows_displays_headers_for_empty_relations(db, run_cli, name):
    assert "user_id" in assert_ok(run_cli("rows", name))


def test_rows_count_zero_displays_headers_without_values(db, run_cli):
    output = assert_ok(run_cli("rows", "main.users", "--count", "0"))
    assert "name" in output
    assert "Alice" not in output
    assert "[red]Bob[/red]" not in output


@pytest.mark.parametrize(
    "flags, limit_expected, expected_rows",
    [
        (("--count", "1"), True, 1),
        (("--count", "0"), True, 0),
        (("--count", "0", "--all"), False, 2),
    ],
)
def test_rows_applies_limit_in_sql(db, run_cli, flags, limit_expected, expected_rows):
    queries = []

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.engine, "before_cursor_execute", record_statement)
    try:
        output = assert_ok(run_cli("rows", "main.users", *flags))
    finally:
        event.remove(db.engine, "before_cursor_execute", record_statement)

    query = next(statement for statement in queries if "FROM main.users" in statement)
    assert ("LIMIT" in query.upper()) is limit_expected
    assert sum(value in output for value in ("Alice", "[red]Bob[/red]")) == expected_rows


def test_rows_rejects_negative_count_without_connecting(run_cli):
    assert_error(run_cli("rows", "users", "--count", "-1"), "Invalid value", code=2)


@pytest.mark.parametrize(
    "command, method, message",
    [
        ("rows", "get_rows", "Failed to load rows"),
        ("count", "get_row_count", "Failed to extract row and column count"),
    ],
)
def test_database_errors_use_cli_message(db, run_cli, monkeypatch, command, method, message):
    def fail(*args, **kwargs):
        raise SQLAlchemyError("raw driver detail")

    monkeypatch.setattr(db, method, fail)
    result = run_cli(command, "main.users")
    assert_error(result, message)
    assert "raw driver detail" not in result.stderr


@pytest.mark.parametrize("command", ["tables", "views", "info", "fks", "rows", "count", "schemas"])
def test_subcommand_help_works_without_database(run_cli, command):
    assert "Usage:" in assert_ok(run_cli(command, "--help"))


@pytest.mark.parametrize(
    "args, message",
    [
        (("tables",), "No database URL configured"),
        (("--url", "invalid", "tables"), "Database connection failed"),
        (("--url", "postgresql://localhost:badport/db", "tables"), "Invalid database URL."),
    ],
)
def test_invalid_connection_configuration_has_clear_errors(run_cli, args, message):
    assert_error(run_cli(*args), message)


def test_explicit_or_environment_url_can_open_existing_sqlite_file(run_cli, tmp_path, monkeypatch):
    path = tmp_path / "example.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE demo (id INTEGER)")
    url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)

    assert "main.demo" in assert_ok(run_cli("--url", url, "tables"))
    assert "main.demo" in assert_ok(run_cli("tables"))
    assert_error(run_cli("--url", "invalid", "tables"), "Database connection failed")


@pytest.mark.parametrize("use_uri", [False, True])
def test_tables_does_not_create_missing_sqlite_file(run_cli, tmp_path, use_uri):
    path = tmp_path / "missing.db"
    url = f"sqlite:///{path.as_posix()}"
    if use_uri:
        url = f"sqlite:///{path.as_uri()}?uri=true&mode=rwc"

    result = run_cli("--url", url, "tables")
    expected_message = "Database connection failed" if use_uri else "SQLite database file not found"
    assert_error(result, expected_message)
    assert not path.exists()
