import pytest

from dbpeek.database import resolve_db_conn


def assert_relation_output(result):
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stderr == ""
    return result.stdout


def test_rel_shows_child_under_the_correct_schema(db, run_cli):
    output = assert_relation_output(run_cli("relations", "users"))

    assert "main.users\n└── main.submissions" in output
    assert "archive.users" in output.splitlines()
    assert output.count("main.submissions") == 1


@pytest.mark.parametrize("args", [("users", "--schema", "archive"), ("archive.users",)])
def test_rel_can_select_one_of_two_matching_roots(db, run_cli, args):
    output = assert_relation_output(run_cli("relations", *args))

    assert output.splitlines() == ["archive.users"]


@pytest.mark.parametrize("args", [("archive.users",), ("--schema", "archive")])
def test_rel_attaches_cross_schema_source_to_the_correct_target(cross_schema_catalog, run_cli, args):
    output = assert_relation_output(run_cli("relations", *args))

    assert "archive.users\n└── main.submissions" in output
    assert "main.users" not in output
    assert output.count("main.submissions") == 1


def test_rel_reports_missing_table(db, run_cli):
    result = run_cli("relations", "missing")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Table 'missing' not found" in result.stderr


def test_rel_reports_unknown_schema_option(db, run_cli):
    result = run_cli("relations", "users", "--schema", "missing")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Schema 'missing' not found" in result.stderr


def test_rel_reports_unknown_schema_in_qualified_name(db, run_cli):
    result = run_cli("relations", "missing.users")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Schema 'missing' not found" in result.stderr


@pytest.mark.parametrize(
    "start, expected",
    [
        ("cycles.employee", ["cycles.employee", "└── cycles.employee ↺ cycle"]),
        ("cycles.cycle_a", ["cycles.cycle_a", "└── cycles.cycle_b", "    └── cycles.cycle_a ↺ cycle"]),
    ],
)
def test_rel_marks_cycle_on_repeated_node(db, run_cli, start, expected):
    output = assert_relation_output(run_cli("relations", start))

    assert output.splitlines() == expected


def test_rel_hides_schema_in_cycle_labels(db, run_cli):
    output = assert_relation_output(run_cli("relations", "employee", "-s", "cycles", "-sns"))

    assert output.splitlines() == ["employee", "└── employee ↺ cycle"]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Rich interprets table names as markup")
def test_rel_preserves_markup_like_table_names(db, run_cli):
    with db.engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE "[red]watch[/red]" (id INTEGER PRIMARY KEY)')

    output = assert_relation_output(run_cli("relations", "main.[red]watch[/red]"))

    assert output.splitlines() == ["main.[red]watch[/red]"]


def test_rel_marks_a_repeated_ancestor_other_than_the_root(db, run_cli):
    with db.engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE cycles.anchor (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql(
            "ALTER TABLE cycles.cycle_a ADD COLUMN anchor_id INTEGER REFERENCES anchor(id)"
        )

    output = assert_relation_output(run_cli("relations", "cycles.anchor"))

    assert output.splitlines() == [
        "cycles.anchor",
        "└── cycles.cycle_a",
        "    └── cycles.cycle_b",
        "        └── cycles.cycle_a ↺ cycle",
    ]


def test_rel_keeps_shared_subtree_under_both_roots(db, run_cli):
    output = assert_relation_output(run_cli("relations", "--schema", "main"))

    for root in ("main.root_left", "main.root_right"):
        assert f"{root}\n└── main.branch\n    └── main.leaf" in output
    assert "main.branch" not in output.splitlines()
    assert "main.leaf" not in output.splitlines()


def test_rel_keeps_shared_subtree_on_both_paths_within_one_root(db, run_cli):
    with db.engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE top (id INTEGER PRIMARY KEY)")
        for name in ("root_left", "root_right"):
            conn.exec_driver_sql(f"ALTER TABLE {name} ADD COLUMN top_id INTEGER REFERENCES top(id)")

    output = assert_relation_output(run_cli("relations", "main.top"))

    assert output.count("main.branch") == 2
    assert output.count("main.leaf") == 2
    assert "↺ cycle" not in output


@pytest.mark.parametrize("args", [("self_ref",), ("--schema", "main")])
def test_rel_handles_a_scope_that_contains_every_table(monkeypatch, run_cli, args):
    database = resolve_db_conn("sqlite://")
    try:
        with database.engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE self_ref (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES self_ref(id))"
            )
        monkeypatch.setattr("dbpeek.cli.resolve_db_conn", lambda url: database)

        output = assert_relation_output(run_cli("relations", *args))

        assert output.splitlines() == ["main.self_ref", "└── main.self_ref ↺ cycle"]
    finally:
        database.engine.dispose()


def test_rel_without_arguments_includes_roots_and_rootless_components(db, run_cli):
    output = assert_relation_output(run_cli("relations"))

    assert "main.users\n└── main.submissions" in output
    roots = [line for line in output.splitlines() if line.startswith("cycles.")]
    assert roots.count("cycles.employee") == 1
    assert sum(root in {"cycles.cycle_a", "cycles.cycle_b"} for root in roots) == 1
    assert "cycles.cycle_a" in output and "cycles.cycle_b" in output
    assert output.count("↺ cycle") == 2


def test_rel_schema_overview_does_not_repeat_a_cycle_as_another_root(db, run_cli):
    output = assert_relation_output(run_cli("relations", "--schema", "cycles"))

    roots = {line for line in output.splitlines() if line.startswith("cycles.")}
    assert roots == {"cycles.cycle_a", "cycles.employee"} or roots == {
        "cycles.cycle_b", "cycles.employee",
    }
    assert "cycles.cycle_a" in output and "cycles.cycle_b" in output
    assert output.count("↺ cycle") == 2
    assert "main." not in output and "archive." not in output


def test_rel_with_an_empty_schema_does_not_render_other_schemas(db, run_cli):
    output = assert_relation_output(run_cli("relations", "--schema", "empty"))

    assert output == ""


@pytest.mark.parametrize("target", ["users", "missing_target"])
def test_rel_reports_an_unresolved_fk_target_schema(db, run_cli, monkeypatch, target):
    get_foreign_keys = db.inspector.get_foreign_keys

    def get_keys(table_name, schema=None):
        keys = get_foreign_keys(table_name, schema=schema)
        if (schema, table_name) == ("main", "submissions"):
            return [dict(key, referred_schema=None, referred_table=target) for key in keys]
        return keys

    monkeypatch.setattr(db.inspector, "get_foreign_keys", get_keys)

    result = run_cli("relations", "main.users")

    assert result.exit_code == 1, (result.output, result.exception)
    assert result.stdout == ""
    assert f"Failed to extract schema for table '{target}'" in result.stderr


def test_rel_can_resolve_unique_fk_target_without_schema(db, run_cli, monkeypatch):
    get_foreign_keys = db.inspector.get_foreign_keys

    def get_keys(table_name, schema=None):
        keys = get_foreign_keys(table_name, schema=schema)
        if (schema, table_name) == ("main", "child"):
            return [dict(key, referred_schema=None) for key in keys]
        return keys

    monkeypatch.setattr(db.inspector, "get_foreign_keys", get_keys)

    output = assert_relation_output(run_cli("relations", "main.parent"))

    root, *children = output.splitlines()
    assert root == "main.parent"
    assert {line.split(maxsplit=1)[1] for line in children} == {
        "main.child",
        "main.implicit_child",
    }


def test_fks_reads_cycle_and_self_reference(db, run_cli):
    result = run_cli("fks", "--schema", "cycles")
    assert result.exit_code == 0, (result.output, result.exception)
    assert "b_id -> cycles.cycle_b.id" in result.stdout
    assert "a_id -> cycles.cycle_a.id" in result.stdout
    assert "manager_id -> cycles.employee.id" in result.stdout


def test_fks_reads_real_cross_schema_foreign_key(postgres_graph, run_cli):
    sales, crm = postgres_graph
    result = run_cli("fks", f"{sales}.orders")

    assert result.exit_code == 0, (result.output, result.exception)
    assert f"user_id -> {crm}.users.id" in result.stdout
    assert f"user_id -> {sales}.users.id" not in result.stdout


def test_rel_includes_real_cross_schema_child_of_selected_root(postgres_graph, run_cli):
    sales, crm = postgres_graph
    output = assert_relation_output(run_cli("relations", f"{crm}.users"))

    assert f"{crm}.users\n└── {sales}.orders" in output
    assert f"{sales}.users" not in output
