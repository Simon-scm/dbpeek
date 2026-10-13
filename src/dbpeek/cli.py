from typing import Annotated
from sqlalchemy.exc import SQLAlchemyError
from .database import resolve_db_conn, DatabaseContext
import typer
from rich.console import Console as RiConsole
from rich.table import Table as RiTable
from rich.tree import Tree as RiTree
import sys


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
            return
        
        except Exception as exc:
            ri_console.print(exc)
            raise typer.Exit(code=1)
    else:
        try:
            table_info = db.get_table_info(table_name)
            ri_console.print(table_info.model_dump_json(indent=2))
            return
        
        except Exception as exc:
            ri_console.print(exc)
            raise typer.Exit(code=1)


@app.command()
def schemas(ctx: typer.Context):
    db: DatabaseContext = ctx.obj
    try:
        schema_names = db.get_schema_names()
        ri_console.print(schema_names)
        return
    
    except Exception as exc:
        print(f"Failed to extract schema names from db: {exc}")
        raise typer.Exit(code=1)



@app.command()
def tables(ctx: typer.Context, 
           relation: Annotated[bool, typer.Option("--rel", "-r")] = False, 
           schema_name: Annotated[str | None, typer.Option("--schema", "-s")] = None):
    
    db: DatabaseContext = ctx.obj

    try:
        schema_names = db.get_schema_names()
    except Exception as exc:
        ri_console.print(f"Failed to extract schema names from db: {exc}")
        typer.Exit(code=1)

    try:   
        if schema_name is not None:
            if schema_name not in schema_names:
                ri_console.print(f"Schema '{schema_name}' is not defined in the db")
                return
            else:
                schema_names = [schema_name]

        table_names = []

        if not schema_names:
            table_names = db.get_table_names()
        else:
            for schema in schema_names:
                table_names.extend(db.get_table_names(schema_name=schema))
    except Exception as exc:
        ri_console.print(f"Failed to extract schema names from db: {exc}")
        typer.Exit(code=1)


    if not relation:
        ri_console.print(table_names)
        return
    else:
        all_table_rels = []
        try:
            for table_name in table_names:
                curr = db.get_table_info(table_name)
                ref_tables = [ ref.get("referred_table") for ref in curr.fk ]
                all_table_rels.append((curr.name, ref_tables))
        except Exception as exc:
                ri_console.print(f"Failed to extract table infos to build relational view: {exc}")
                raise typer.Exit(code=1)
        
        rel_trees = []
        visited = set()
        try:
            for table_name, relations in all_table_rels:
                if len(relations) == 0:
                    tree = RiTree(table_name)

                    append_to_tree(table_name=table_name, tree=tree, table_rels=all_table_rels, visited=visited)

                    rel_trees.append(tree)

            for tree in rel_trees:
                ri_console.print(tree)

            return
                    
        except Exception as exc:
            ri_console.print(f"Failed to build relational view: {exc}")
            raise typer.Exit(code=1)
                

@app.command()
def views(ctx: typer.Context):
    db: DatabaseContext = ctx.obj
    insp = db.inspector
    ri_console.print(insp.get_view_names())
    return


@app.command()
def rows(
        ctx: typer.Context, 
        table_name: Annotated[str, typer.Argument()], 
        row_count: Annotated[int, typer.Option("--count", "-c")] = 10,
        all: Annotated[bool, typer.Option("--all", "-a")] = False):
    
    db: DatabaseContext = ctx.obj

    if row_count < 0:
        raise Exception(f"No negative number for rows to be printed allowed")
    
    try:
        if all:
            rows = db.get_rows(table_name)
        else:
            rows = db.get_rows(table_name, row_count)

        if not rows:
            raise Exception(f"Failed to load rows for table '{table_name}':")
        
    except Exception as exc:
        ri_console.print(exc)
        raise typer.Exit(code=1)

    try:
        rich_table = RiTable(title=table_name)
        for column_name in rows[0]:
            rich_table.add_column(column_name)

        for row in rows[1:]:
            rich_table.add_row(
                *("NULL" if value is None else str(value) for value in row)
            )

        ri_console.print(rich_table)
        return

    except Exception as exc:
        ri_console.print(f"Failed to print rows of table '{table_name}' to the terminal: {exc}")
        raise typer.Exit(code=1)


@app.command()
def count(ctx: typer.Context, table_name: Annotated[str, typer.Argument()]):
    db: DatabaseContext = ctx.obj

    try:
        row_count = db.get_row_count(table_name)
        column_count = db.get_column_count(table_name)

        ri_console.print(f"Table: {table_name}")
        ri_console.print(f"Rows: {row_count}")
        ri_console.print(f"Columns: {column_count}")
        return

    except Exception as exc:
        ri_console.print(f"Failed to extract row and column count of table '{table_name}': {exc}")
        raise typer.Exit(code=1)



def append_to_tree(table_name, tree, table_rels, visited) -> None:
    if table_name in visited:
        return

    visited.add(table_name)

    for child_table_name, relations in table_rels:
        if table_name in relations:
            child = tree.add(child_table_name)
            append_to_tree(table_name=child_table_name, tree=child, table_rels=table_rels, visited=visited)
         
    