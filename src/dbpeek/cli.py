from typing import Annotated
import json
from .database import resolve_db_conn, DatabaseContext, TableInfo, InputRef, ResolvedRef, DBpeekError
from sqlalchemy.exc import SQLAlchemyError
import typer
from rich.console import Console as RiConsole
from rich.table import Table as RiTable
from rich.text import Text
from rich.tree import Tree as RiTree
from contextlib import contextmanager

# TODO: 
# - Create real sqlite test db and pre define env variable?? -> at least give guidance on how to set it
# - All functions/commands need a header comment roughly explaining what the command does
# - Include schema handling in --help -> define "helps" for all commands
# - Maybe add select query option?


# Entrance point of the program 
app = typer.Typer(invoke_without_command=True)
ri_console = RiConsole()
ri_error_console = RiConsole(stderr=True)

#------------Helper Functions------------#
def get_db(ctx: typer.Context) -> DatabaseContext:
    with handle_cli_errors("Database connection failed."):
        return resolve_db_conn(ctx.obj)

# DBPeekErrors (wrong use of the application) are explicity raised and addressed here 
# Errors occuring while interacting with the db (SQLAlchemyErrors) are caught here and will be replaced by "database_error", a var
# that can be defined in each command line function -> this is so SQLAlchemy do not propagte raw to the user
@contextmanager
def handle_cli_errors(database_error: str):
    try:
        yield
    except DBpeekError as exc:
        ri_error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from None # "from None" so full trace back is not shown to user
    except SQLAlchemyError:
        ri_error_console.print(database_error, markup=False)
        raise typer.Exit(code=1) from None
    


def append_to_tree(ref: ResolvedRef, toggle_schema: bool, tree: RiTree, 
                   table_rels: list[tuple[ResolvedRef,list[ResolvedRef]]], 
                   visited: set[str]) -> None:
    table_name = ref.schema_name + "." + ref.name
    # check if table was already visited to prevent cycles
    if table_name in visited:
        return

    visited.add(table_name)

    # Every table which referres to the current table will get checked recursively
    for child_ref, child_relations in table_rels:
        if ref in child_relations:
            if toggle_schema:
                child = tree.add(child_ref.name)
            else:
                child = tree.add(child_ref.schema_name + "." + child_ref.name)
            append_to_tree(ref=child_ref, toggle_schema=toggle_schema, tree=child,
                            table_rels=table_rels, visited=visited)

#----------------------------------------#

#---------Commad Line Functions----------#

# Runs everytime a command is called (also when the application gets run without any command)
@app.callback()
def main(ctx: typer.Context, url: Annotated[str | None, typer.Option("--url", "-u")] = None):
    # store url in typer context object so other functions can retrieve it and create a db connenction 
    ctx.obj = url

    # if program was started without any command the app will run the info function
    if ctx.invoked_subcommand is None:
        info(ctx)


@app.command()
def info(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None, schema_name: Annotated[str, typer.Option("--schema", "-s")] = None):
    
    db: DatabaseContext = get_db(ctx)
    if table_name is None:
        with handle_cli_errors("Failed to extract database metadata"):
            metadata = db.get_db_metadata()
            typer.echo(metadata.model_dump_json(indent=2))
            return
    else:
        # If no schema is provided in table_name and also not in the --schema option, the name will be searched in all schemas and all information will be returned
        # If --schema option is set everything in table_name will be interpreted as the pure tablename 
        input_ref: InputRef = db.parse_input_ref(input_name=table_name, input_schema=schema_name)
        with handle_cli_errors("Failed to extract table information"):
            resolved_refs: list[ResolvedRef] = db.resolve_table_ref(input_ref)
            if not resolved_refs:
                raise DBpeekError("Provided table does not exist")
            
            table_infos: list[TableInfo] = []
            for ref in resolved_refs:
                table_infos.append(db.get_table_info(ref))

            if len(table_infos) == 1:
                typer.echo(table_infos[0].model_dump_json(indent=2))
            else:
                typer.echo(json.dumps([info.model_dump(mode="json") for info in table_infos], indent=2, ensure_ascii=False))
            return


@app.command()
def schemas(ctx: typer.Context):
    
    db: DatabaseContext = get_db(ctx)
    with handle_cli_errors("Failed to extract schema names from db"):
        schema_names = db.get_all_schema_names()
        ri_console.print(schema_names)
        return


@app.command()
def tables(ctx: typer.Context, 
           relation: Annotated[bool, typer.Option("--rel", "-r")] = False, 
           schema_name: Annotated[str | None, typer.Option("--schema", "-s")] = None,
           toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = get_db(ctx)
    
    with handle_cli_errors("Failed to extract schema names from db"):
        schema_names: list[str] = db.get_all_schema_names()
    
    with handle_cli_errors("Failed to extract table references from db"):
        if schema_name is not None and schema_name not in schema_names:
            raise DBpeekError(f"Schema '{schema_name}' not found.")

        table_refs: list[ResolvedRef]= db.get_all_tables(schema=schema_name)
        
    if not relation:
        if toggle_schema_output:
            ri_console.print([ ref.name for ref in table_refs ])
        else:
            ri_console.print([ ref.schema_name + "." + ref.name for ref in table_refs ])
        return

    # Build up relational tree 
    else:
        all_table_rels: list[tuple[ResolvedRef,list[ResolvedRef]]] = []
        # Get table info for all tables in scope to determine their relations to one another 
        # so get_table_info() always returns list of len 1 
        with handle_cli_errors(f"Failed to extract table infos to build relational view"):
            for reference in table_refs:
                info = db.get_table_info(reference) 

                referred_tables: list[ResolvedRef] = []
                for referral in info.fk:
                    new_ref = ResolvedRef(name=referral.get("referred_table"), schema_name=referral.get("referred_schema"))
                    referred_tables.append(new_ref)

                # Build adjacency list of tables paired with tables they refer to
                all_table_rels.append((reference, referred_tables))

        # Build rich tree structure to print to console
        rel_trees = []
        # Go through every table on the top level of the recursion because we can have different trees (not connected to eachother)
        for ref, relations in all_table_rels:
            # If a table does not refer to any other tables its a root which could be referred by other tables
            if not relations:    
                # initiate new tree root either with schema name or without depending on the toggle
                if toggle_schema_output:
                    tree = RiTree(ref.name) 
                else:
                    tree = RiTree(ref.schema_name + "." + ref.name)

                visited: set[str] = set()
                # search for referrences and append recursively to the tree root (in-place)
                append_to_tree(ref=ref, toggle_schema=toggle_schema_output, tree=tree, 
                                table_rels=all_table_rels, visited=visited) 

                rel_trees.append(tree) # append tree root to the list of all trees

        for tree in rel_trees:
            ri_console.print(tree)

        return


@app.command()
def views(ctx: typer.Context, schema_name: Annotated[str, typer.Option("--schema", "-s")] = None, 
          toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = get_db(ctx)

    with handle_cli_errors("Failed to extract view references from db"):
        view_refs: list[ResolvedRef] = db.get_all_views(schema=schema_name)

    if toggle_schema_output:
        ri_console.print([ ref.name for ref in view_refs ])
    else:
        ri_console.print([ ref.schema_name + "." + ref.name for ref in view_refs ])
    return


@app.command()
def fks(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None,
        schema_name: Annotated[str, typer.Option("--schema", "-s")] = None,
        toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = get_db(ctx)

    with handle_cli_errors("Failed to extract table references"):
        # If no table name is specified -> gets all tables of the specified schema, if no schema is speicified as well, all tables of all schemas are returned
        if table_name is None:
            resolved_refs: list[ResolvedRef] = db.get_all_tables(schema=schema_name)

        # If table is specified returns all tables references with the given name (out of all schemas) or one table reference if schema is specified as well
        else:
            input_ref: InputRef = db.parse_input_ref(input_name=table_name, input_schema=schema_name)
            resolved_refs: list[ResolvedRef]  = db.resolve_table_ref(input_ref=input_ref)
            if not resolved_refs:
                raise DBpeekError("Provided table does not exist")
            

    table_infos: list[TableInfo] = []
    with handle_cli_errors("Failed to extract foreign keys"):
        for ref in resolved_refs:
            table_infos.append(db.get_table_info(ref))

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
                target = fk["referred_table"]
                target_schema = fk.get("referred_schema")
                if target_schema is not None and not toggle_schema_output:
                    target = f"{target_schema}.{target}"

                pairs = zip(fk["constrained_columns"], fk["referred_columns"], strict=True)
                mappings = ", ".join(f"{source} -> {target}.{column}" for source, column in pairs)
                tree.add(Text(f"{mappings} (name: {fk.get('name')})"))

        ri_trees.append(tree)

    for tree in ri_trees:
        ri_console.print(tree)
    
    return
    

@app.command()
def rows(
        ctx: typer.Context, 
        name: Annotated[str, typer.Argument()],
        schema_name: Annotated[str, typer.Option("--schema", "-s")] = None,
        row_count: Annotated[int, typer.Option("--count", "-c", min=0)] = 10,
        all: Annotated[bool, typer.Option("--all", "-a")] = False):

    db: DatabaseContext = get_db(ctx)
   
    input_ref: InputRef = db.parse_input_ref(input_name=name, input_schema=schema_name)
    with handle_cli_errors("Failed to resolve table or view"):
        resolved_ref: ResolvedRef = db.resolve_relation_ref(input_ref)

    with handle_cli_errors(f"Failed to load rows of table/view: {resolved_ref.schema_name}.{resolved_ref.name}"):
        if all:
            rows: list = db.get_rows(resolved_ref)
        else:
            rows: list = db.get_rows(resolved_ref, row_count)

        # rows will only be empty if there are no columns extracted as well -> thats not just an empty table but an error 
        if not rows:
            raise DBpeekError(f"Failed to load rows of {"table" if db.is_table(resolved_ref) else "view"}: {resolved_ref.schema_name}.{resolved_ref.name}")

    rich_table = RiTable(title=Text(f"{resolved_ref.schema_name}.{resolved_ref.name}"))
    for column_name in rows[0]:
        rich_table.add_column(Text(column_name))

    for row in rows[1:]:
        rich_table.add_row(
            *(Text("NULL" if value is None else str(value)) for value in row)
        )

    ri_console.print(rich_table)
    return


@app.command()
def count(ctx: typer.Context, name: Annotated[str, typer.Argument()], schema_name: Annotated[str, typer.Option("--schema", "-s")] = None):
    db: DatabaseContext = get_db(ctx)

    input_ref: InputRef = db.parse_input_ref(input_name=name, input_schema=schema_name)
    with handle_cli_errors("Failed to resolve table or view"):
        resolved_ref: ResolvedRef = db.resolve_relation_ref(input_ref)
    
    with handle_cli_errors(f"Failed to extract row and column count of table/view: {resolved_ref.schema_name}.{resolved_ref.name}"):
        row_count: int = db.get_row_count(resolved_ref)
        column_count: int = db.get_column_count(resolved_ref)

        ri_console.print(f"{"Table" if db.is_table(resolved_ref) else "View"}: {resolved_ref.schema_name}.{resolved_ref.name}")
        ri_console.print(f"Columns: {column_count}")
        ri_console.print(f"Rows: {row_count}")
        
        return





         
