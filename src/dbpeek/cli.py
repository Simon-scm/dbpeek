from typing import Annotated
from sqlalchemy.exc import SQLAlchemyError
from .database import resolve_db_conn, DatabaseContext, TableInfo, TableRef
import typer
from rich.console import Console as RiConsole
from rich.table import Table as RiTable
from rich.tree import Tree as RiTree


# Entrance point of the program 
app = typer.Typer(invoke_without_command=True)
ri_console = RiConsole()


# Function that runs everytime a command is called (also when the application gets run without any command)
@app.callback()
def main(ctx: typer.Context, url: Annotated[str | None, typer.Option("--url", "-u")] = None):
    try:
        # db connection will be set up
        db_conn: DatabaseContext = resolve_db_conn(url)
        ctx.obj = db_conn
        
    except (SQLAlchemyError, RuntimeError) as exc:
        ri_console.print(
            f"Database connection failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=1)

    # if program was started without any command the app will run the info function
    if ctx.invoked_subcommand is None:
        info(ctx)


@app.command()
def info(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None, schema_name: Annotated[str, typer.Option("--schema", "-s")] = None):
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
        # If no schema is provided, table name will be search in all schemas and all information will be returned
        table_ref: TableRef = db.parse_table_ref(input_name=table_name, input_schema=schema_name)
        try:
            table_info: list[TableInfo] = db.get_table_info(table_ref=table_ref)
            for info in table_info:
                ri_console.print(info.model_dump_json(indent=2))
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
           input_schema_name: Annotated[str | None, typer.Option("--schema", "-s")] = None,
           toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = ctx.obj
    
    try:
        schema_names = db.get_schema_names()
    except Exception as exc:
        ri_console.print(f"Failed to extract schema names from db: {exc}")
        typer.Exit(code=1)

    
    if input_schema_name is not None and input_schema_name not in schema_names:
        ri_console.print(f"Schema '{input_schema_name}' is not defined in the db")
        return

    
    try: # if schema_name == None this returns a list of all tables of all schemas (potentially different ones)
        table_refs: list[TableRef] = db.get_table_refs(schema_name=input_schema_name) 
    except Exception as exc:
        ri_console.print(f"Failed to extract table references from db: {exc}")
        typer.Exit(code=1)

    
    if not relation:
        if toggle_schema_output:
            ri_console.print([ ref.name for ref in table_refs ])
        else:
            ri_console.print([ ref.schema_name + "." + ref.name for ref in table_refs ])
        return

    # TODO: Implement toggle option for schema name output and revise recursive code for new TableRef and schema handling
    else:
        all_table_rels: list[tuple] = []
        # Get table info for all tables in scope to determine their relations to one another
        try:
            for reference in table_refs:
                infos = db.get_table_info(reference) 
                reffered_tables = [ refferal.get("referred_table") for refferal in infos[0].fk ]
                # Build adjacency list of tables paired with tables they reffer
                all_table_rels.append((infos[0].name, infos[0].schema_name, reffered_tables))

        except Exception as exc:
                ri_console.print(f"Failed to extract table infos to build relational view: {exc} {type(exc)}")
                raise typer.Exit(code=1)

        # Build rich tree structure to print to console
        rel_trees = []
        visited = set()
        try:
            for table_name, schema_name, relations in all_table_rels:

                # If schema name output should be deactivated, the varaible is set to "" else the trailing "." is already appended 

                # If a table does not reffer any other tables its a root which could be reffered by other tables
                if len(relations) == 0:    
                    # initiate new tree root    
                    if toggle_schema_output:
                        tree = RiTree(table_name) 
                    else:
                        tree = RiTree(schema_name + "." + table_name)

                    append_to_tree(table_name=table_name, schema_name=schema_name, 
                                   toggle_schema=toggle_schema_output, tree=tree, 
                                   table_rels=all_table_rels, visited=visited) # append recursively to the tree root (in-place)

                    rel_trees.append(tree) # append tree root to the list of all trees

            for tree in rel_trees:
                ri_console.print(tree)

            return
                    
        except Exception as exc:
            ri_console.print(f"Failed to build relational view: {exc}")
            raise typer.Exit(code=1)


def append_to_tree(table_name: str, schema_name: str, toggle_schema: bool, tree: RiTree, table_rels: list[tuple], visited: list[str]) -> None:
    table_ref = schema_name + "." +  table_name
    
    if table_ref in visited:
        return

    visited.add(table_ref)

    for child_table_name, child_schema_name, relations in table_rels:
        if table_name in relations:
            if toggle_schema:
                child = tree.add(child_table_name)
            else:
                child = tree.add(child_schema_name + "." + child_table_name)
            append_to_tree(table_name=child_table_name, schema_name=child_schema_name, 
                            toggle_schema=toggle_schema, tree=child,
                            table_rels=table_rels, visited=visited)


# TODO: Implement schema selector
@app.command()
def views(ctx: typer.Context):
    db: DatabaseContext = ctx.obj
    insp = db.inspector
    ri_console.print(insp.get_view_names())
    return

# TODO: Implement new TableRef and schema handling
@app.command()
def fks(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None):
    db: DatabaseContext = ctx.obj

    if table_name is None:
        table_names = db.get_table_refs()
    else:
        table_names = [table_name]

    table_infos: list[TableInfo] = []
    for name in table_names:
        table_infos.append(db.get_table_info(name))

    ri_trees: list[RiTree] = []
    for table in table_infos:
        tree = RiTree(table.name)
        if not table.fk:
            tree.add("null")
        else:
            for fk in table.fk:
                child = f"{fk.get("constrained_columns")[0]} -> {fk.get("referred_table")}.{fk.get("referred_columns")[0]} (name: {fk.get("name")})"
                tree.add(child)

        ri_trees.append(tree)


    for tree in ri_trees:
        ri_console.print(tree)
    
    return
    
# TODO: Implement new TableRef and schema handling
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

# TODO: Implement new TableRef and schema handling
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




         