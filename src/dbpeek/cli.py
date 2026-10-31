from typing import Annotated
from sqlalchemy.exc import SQLAlchemyError
from .database import resolve_db_conn, DatabaseContext, TableInfo, TableRef
import typer
from rich.console import Console as RiConsole
from rich.table import Table as RiTable
from rich.tree import Tree as RiTree

# TODO: 
# - Create real sqlite test db and pre define env variable??
# - All functions/commands need a header comment roughly explaining what the command does
# - Include schema handling in --help -> define "helps" for all commands


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
        # If no schema is provided in tabl_name and also not in --schema option the name will be searched in all schemas and all information will be returned
        # If --schema option is set everything in table_name will be interpreted as the pure tablename 
        # -> false behaivior occurs if schema name is provide in table_name AND schema_name! 
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
        raise typer.Exit(code=1)

    
    if input_schema_name is not None and input_schema_name not in schema_names:
        ri_console.print(f"Schema '{input_schema_name}' is not defined in the db")
        return

    
    try: # if schema_name == None this returns a list of all tables of all schemas (potentially different ones)
        table_refs: list[TableRef] = db.get_table_refs(schema_name=input_schema_name) 
    except Exception as exc:
        ri_console.print(f"Failed to extract table references from db: {exc}")
        raise typer.Exit(code=1)

    
    if not relation:
        if toggle_schema_output:
            ri_console.print([ ref.name for ref in table_refs ])
        else:
            ri_console.print([ ref.schema_name + "." + ref.name for ref in table_refs ])
        return

    # Build up relational tree 
    else:
        all_table_rels: list[tuple] = []
        # Get table info for all tables in scope to determine their relations to one another -> all tables in table_refs come with schema 
        # so get_table_info() always returns list of len 1 
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
        try: # We got through every table on the top level of the recursion because we can have different trees (not connected to eachother)
            for table_name, schema_name, relations in all_table_rels:
                # If a table does not reffer any other tables its a root which could be reffered by other tables
                if len(relations) == 0:    
                    # initiate new tree root either with schema name or without depending on the toggle
                    if toggle_schema_output:
                        tree = RiTree(table_name) 
                    else:
                        tree = RiTree(schema_name + "." + table_name)

                    # search for reffernces and append recursively to the tree root (in-place)
                    append_to_tree(table_name=table_name, schema_name=schema_name, 
                                   toggle_schema=toggle_schema_output, tree=tree, 
                                   table_rels=all_table_rels, visited=visited) 

                    rel_trees.append(tree) # append tree root to the list of all trees

            for tree in rel_trees:
                ri_console.print(tree)

            return
                    
        except Exception as exc:
            ri_console.print(f"Failed to build relational view: {exc}")
            raise typer.Exit(code=1)


def append_to_tree(table_name: str, schema_name: str, toggle_schema: bool, tree: RiTree, table_rels: list[tuple], visited: list[str]) -> None:
    table_ref = schema_name + "." +  table_name
    # check if table was already visited to prevent cycles
    if table_ref in visited:
        return

    visited.add(table_ref)

    # Every table which reffers to the current table will get checked recursively
    for child_table_name, child_schema_name, relations in table_rels:
        if table_name in relations:
            if toggle_schema:
                child = tree.add(child_table_name)
            else:
                child = tree.add(child_schema_name + "." + child_table_name)
            append_to_tree(table_name=child_table_name, schema_name=child_schema_name, 
                            toggle_schema=toggle_schema, tree=child,
                            table_rels=table_rels, visited=visited)



@app.command()
def views(ctx: typer.Context, schema_name: Annotated[str, typer.Option("--schema", "-s")] = None, 
          toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = ctx.obj

    try:
        view_refs = db.get_view_refs(schema_name=schema_name)
        if toggle_schema_output:
            ri_console.print([ ref.name for ref in view_refs ])
        else:
            ri_console.print([ ref.schema_name + "." + ref.name for ref in view_refs ])
        return
    except Exception as exc:
        ri_console.print(f"Failed to extract view references from db: {exc}")
        raise typer.Exit(code=1)



# Show
@app.command()
def fks(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None,
        schema_name: Annotated[str, typer.Option("--schema", "-s")] = None,
        toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = ctx.obj

    # If no table name is specified -> returns all tables else only get the refernce object for the specified table
    # If table is specified but no schema is specified -> returns all tables with the given name (out of all schemas)
    if table_name is None:
        table_refs = db.get_table_refs(schema_name=schema_name)
    else:
        ref = db.parse_table_ref(input_name=table_name, input_schema=schema_name)

    table_infos: list[TableInfo] = []
    for ref in table_refs:
        table_infos.extend(db.get_table_info(ref)) # extend because get_table_info() returns list

    ri_trees: list[RiTree] = []
    for table in table_infos:

        if toggle_schema_output:
            tree = RiTree(table.name)
        else:
            tree = RiTree(table.schema_name + "." + table.name)

        if not table.fk:
            tree.add("null")
        else:
            for fk in table.fk:
                if toggle_schema_output:
                    child = f"{fk.get("constrained_columns")[0]} -> {fk.get("referred_table")}.{fk.get("referred_columns")[0]} (name: {fk.get("name")})"
                else:
                    child = f"{fk.get("constrained_columns")[0]} -> {fk.get("referred_schema")}.{fk.get("referred_table")}.{fk.get("referred_columns")[0]} (name: {fk.get("name")})"
                tree.add(child)

        ri_trees.append(tree)

    for tree in ri_trees:
        ri_console.print(tree)
    
    return
    

@app.command()
def rows(
        ctx: typer.Context, 
        name: Annotated[str, typer.Argument()],
        schema_name: Annotated[str, typer.Option("--schema", "-s")] = None,
        row_count: Annotated[int, typer.Option("--count", "-c")] = 10,
        all: Annotated[bool, typer.Option("--all", "-a")] = False):

    if row_count < 0:
        raise Exception(f"No negative number for rows to be printed allowed")
    
    db: DatabaseContext = ctx.obj
   
    ref = db.parse_table_ref(input_name=name, input_schema=schema_name)

    table_schemas = db.get_table_schemas(ref.name)

    if len(table_schemas) > 1 and ref.schema_name is None:
        ri_console.print(f"Table/View with name: '{ref.name}' exists in more than one schema: {table_schemas}. Please specify one to extract rows.")
        raise typer.Exit(code=1)

    if (len(table_schemas) < 1) or (ref.schema_name is not None and ref.schema_name not in table_schemas):
        ri_console.print(f"Provided{" schema: " + ref.schema_name + " with" if ref.schema_name is not None else ""} table/view: {ref.name} does not exist")
        raise typer.Exit(code=1)

    try:
        if all:
            rows = db.get_rows(ref)
        else:
            rows = db.get_rows(ref, row_count)

        if not rows:
            raise Exception(f"Failed to load rows for table '{ref.name}' with schema: '{table_schemas[0]}'")
        
    except Exception as exc:
        ri_console.print(exc)
        raise typer.Exit(code=1)

    try:
        rich_table = RiTable(title=table_schemas[0] + "." + ref.name)
        for column_name in rows[0]:
            rich_table.add_column(column_name)

        for row in rows[1:]:
            rich_table.add_row(
                *("NULL" if value is None else str(value) for value in row)
            )

        ri_console.print(rich_table)
        return

    except Exception as exc:
        ri_console.print(f"Failed to print rows of table '{ref.name}' with schema: '{table_schemas[0]} to the terminal: {exc}")
        raise typer.Exit(code=1)


@app.command()
def count(ctx: typer.Context, name: Annotated[str, typer.Argument()], schema_name: Annotated[str, typer.Option("--schema", "-s")] = None):
    db: DatabaseContext = ctx.obj

    ref = db.parse_table_ref(name, schema_name)

    table_schemas = db.get_table_schemas(ref.name)
    
    if len(table_schemas) > 1 and ref.schema_name is None:
        ri_console.print(f"Table/View with name: '{ref.name}' exists in more than one schema: {table_schemas}. Please specify one to extract rows.")
        raise typer.Exit(code=1)

    if (len(table_schemas) < 1) or (ref.schema_name is not None and ref.schema_name not in table_schemas):
        ri_console.print(f"Provided{" schema: " + ref.schema_name + " with" if ref.schema_name is not None else ""} table/view: {ref.name} does not exist")
        raise typer.Exit(code=1)
    
    try:
        row_count = db.get_row_count(ref)
        column_count = db.get_column_count(ref)

        ri_console.print(f"Table: {table_schemas[0]}.{ref.name}")
        ri_console.print(f"Rows: {row_count}")
        ri_console.print(f"Columns: {column_count}")
        return

    except Exception as exc:
        ri_console.print(f"Failed to extract row and column count of '{table_schemas[0]}.{ref.name}': {exc}")
        raise typer.Exit(code=1)




         