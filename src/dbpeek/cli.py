from typing import Annotated
from sqlalchemy.exc import SQLAlchemyError
from .database import resolve_db_conn, DatabaseContext
import typer
from rich.console import Console as RiConsole
from rich.table import Table as RiTable
from rich.tree import Tree as RiTree


app = typer.Typer(invoke_without_command=True)
ri_console = RiConsole()


@app.callback()
def main(ctx: typer.Context, url: Annotated[str | None, typer.Option("--url", "-u")] = None):
    try:
        db_conn: DatabaseContext = resolve_db_conn(url)
        ctx.obj = db_conn
        
    except (SQLAlchemyError, RuntimeError) as exc:
        ri_console.print(
            f"Database connection failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=1)

    if ctx.invoked_subcommand is None:
        info(ctx)


@app.command()
def info(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None):
    db: DatabaseContext = ctx.obj
    if table_name is None:
        try:
            metadata = db.get_db_metadata()
            ri_console.print(metadata.model_dump_json(indent=2))
        except Exception as exc:
            ri_console.print(exc)
    else:
        try:
            table_info = db.get_table_info(table_name)
            ri_console.print(table_info.model_dump_json(indent=2))
        except Exception as exc:
            ri_console.print(exc)


@app.command()
def tables(ctx: typer.Context, relation: Annotated[bool, typer.Option("--rel", "-r")] = False):
    db: DatabaseContext = ctx.obj
    table_names = db.get_table_names()
    if not relation:
        ri_console.print(table_names)
    else:
        all_table_rels = []
        for table_name in table_names:
            curr = db.get_table_info(table_name)
            ref_tables = [ ref.get("referred_table") for ref in curr.fk ]
            all_table_rels.append((curr.name, ref_tables))
        
        rel_trees = []
        visited = set()

        for table_name, relations in all_table_rels:
            if len(relations) == 0:
                tree = RiTree(table_name)

                append_to_tree(table_name=table_name, tree=tree, table_rels=all_table_rels, visited=visited)

                rel_trees.append(tree)

        for tree in rel_trees:
            ri_console.print(tree)
        
                

@app.command()
def views(ctx: typer.Context):
    db: DatabaseContext = ctx.obj
    insp = db.inspector
    ri_console.print(insp.get_view_names())


@app.command()
def rows(
    ctx: typer.Context, 
    table_name: Annotated[str, typer.Argument()], 
    row_count: Annotated[int, typer.Option("--rows", "-r")] = 20):
    db: DatabaseContext = ctx.obj

    try:
        rows = db.get_rows(table_name, row_count)
        if not rows:
            raise Exception(f"Failed to load rows for table {table_name}")
    except Exception as exc:
        ri_console.print(exc)

    try:
        rich_table = RiTable(title=table_name)
        for column_name in rows[0]:
            rich_table.add_column(column_name)

        for row in rows[1:]:
            rich_table.add_row(
                *("NULL" if value is None else str(value) for value in row)
            )

        ri_console.print(rich_table)

    except Exception as exc:
        ri_console.print(f"Failed to print rows of table '{table_name}' to the terminal: {exc}")




def append_to_tree(table_name, tree, table_rels, visited) -> None:
    if table_name in visited:
        return

    visited.add(table_name)

    for child_table_name, relations in table_rels:
        if table_name in relations:
            child = tree.add(child_table_name)
            append_to_tree(table_name=child_table_name, tree=child, table_rels=table_rels, visited=visited)
         
    