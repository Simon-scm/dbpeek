import pytest


def test_rel_shows_child_under_the_correct_schema(db, run_cli):
    result = run_cli("tables", "--rel")
    assert result.exit_code == 0, (result.output, result.exception)
    assert "main.users\n└── main.submissions" in result.stdout
    assert "archive.users" in result.stdout
    assert result.stdout.count("main.submissions") == 1


def test_rel_attaches_cross_schema_source_to_the_correct_target(cross_schema_catalog, run_cli):
    result = run_cli("tables", "--rel")
    assert result.exit_code == 0, (result.output, result.exception)
    assert "archive.users\n└── main.submissions" in result.stdout
    assert "main.users" in result.stdout
    assert result.stdout.count("main.submissions") == 1


def test_fks_reads_cycle_and_self_reference(db, run_cli):
    result = run_cli("fks", "--schema", "cycles")
    assert result.exit_code == 0, (result.output, result.exception)
    assert "b_id -> cycles.cycle_b.id" in result.stdout
    assert "a_id -> cycles.cycle_a.id" in result.stdout
    assert "manager_id -> cycles.employee.id" in result.stdout


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="tree starts only at nodes without a foreign key")
@pytest.mark.parametrize("table_names", [("cycle_a", "cycle_b"), ("employee",)])
def test_rel_includes_components_without_a_root(db, run_cli, table_names):
    result = run_cli("tables", "--rel", "--schema", "cycles")
    assert result.exit_code == 0, (result.output, result.exception)
    for name in table_names:
        assert f"cycles.{name}" in result.stdout


def test_rel_keeps_shared_subtree_under_both_roots(db, run_cli):
    result = run_cli("tables", "--rel", "--schema", "main")
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stdout.count("main.branch") == 2
    assert result.stdout.count("main.leaf") == 2


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="visited is shared by paths within one root")
def test_rel_keeps_shared_subtree_on_both_paths_within_one_root(db, run_cli):
    with db.engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE top (id INTEGER PRIMARY KEY)")
        for name in ("root_left", "root_right"):
            conn.exec_driver_sql(f"ALTER TABLE {name} ADD COLUMN top_id INTEGER REFERENCES top(id)")

    result = run_cli("tables", "--rel", "--schema", "main")
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stdout.count("main.branch") == 2
    assert result.stdout.count("main.leaf") == 2


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="tree drops targets outside the selected schema")
def test_rel_retains_cross_schema_target_from_inspector(cross_schema_catalog, run_cli):
    result = run_cli("tables", "--rel", "--schema", "main")

    assert result.exit_code == 0, (result.output, result.exception)
    assert "main.submissions" in result.stdout
    assert "archive.users" in result.stdout


def test_fks_reads_real_cross_schema_foreign_key(postgres_graph, run_cli):
    sales, crm = postgres_graph
    result = run_cli("fks", f"{sales}.orders")

    assert result.exit_code == 0, (result.output, result.exception)
    assert f"user_id -> {crm}.users.id" in result.stdout
    assert f"user_id -> {sales}.users.id" not in result.stdout


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="tree drops targets outside the selected schema")
def test_rel_keeps_cross_schema_target_with_source_filter(postgres_graph, run_cli):
    sales, crm = postgres_graph
    result = run_cli("tables", "--rel", "--schema", sales)

    assert result.exit_code == 0, (result.output, result.exception)
    assert f"{sales}.orders" in result.stdout
    assert f"{crm}.users" in result.stdout
