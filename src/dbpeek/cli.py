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
# - Give guidance on how to set env variable DBPEEKDATABASE
# - All functions/commands need a header comment roughly explaining what the command does
# - Include schema handling in --help -> define "helps" for all commands
# - Maybe add select query option?
# - Time out einbauen - wenn localhost versucht wird und dieser nicht up ist, startet ein endless try (vermutlich)
# - Überprüfen warum keine login Informationen nötig waren um zu Postgers docker db auf localhost zuzugreifen


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
# that can be defined in each command line function -> this is so SQLAlchemy do not propagate raw to the user
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
def tables(ctx: typer.Context, schema_name: Annotated[str | None, typer.Option("--schema", "-s")] = None,
           toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = get_db(ctx)
    
    with handle_cli_errors("Failed to extract schema names from db"):
        schema_names: list[str] = db.get_all_schema_names()

        if schema_name is not None and schema_name not in schema_names:
            raise DBpeekError(f"Schema '{schema_name}' not found.")
    
    with handle_cli_errors("Failed to extract table references from db"):
        table_refs: list[ResolvedRef]= db.get_all_tables(schema=schema_name)
        
    if toggle_schema_output:
        ri_console.print([ ref.name for ref in table_refs ])
    else:
        ri_console.print([ f"{ref.schema_name}.{ref.name}" for ref in table_refs ])
    return


@app.command()
def views(ctx: typer.Context, schema_name: Annotated[str, typer.Option("--schema", "-s")] = None, 
          toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = get_db(ctx)

    with handle_cli_errors("Failed to extract schema names from db"):
            schema_names: list[str] = db.get_all_schema_names()
            if schema_name is not None and schema_name not in schema_names:
                raise DBpeekError(f"Schema '{schema_name}' not found.")   
            
    with handle_cli_errors("Failed to extract view references from db"):
        view_refs: list[ResolvedRef]= db.get_all_views(schema=schema_name)
        
    if toggle_schema_output:
        ri_console.print([ ref.name for ref in view_refs ])
    else:
        ri_console.print([ f"{ref.schema_name}.{ref.name}" for ref in view_refs ])
    return


@app.command()
def relations(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None,
                schema_name: Annotated[str, typer.Option("--schema", "-s")] = None,
                toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):

    db = get_db(ctx)

    with handle_cli_errors("Failed to extract schema names from db"):
        schema_names: list[str] = db.get_all_schema_names()

        if schema_name is not None and schema_name not in schema_names:
            raise DBpeekError(f"Schema '{schema_name}' not found")

    with handle_cli_errors("Failed to extract table references from db"):
        # Directly get all tables regardless of their schema and the requested schema because the relation can also go across schemas
        all_table_refs: list[ResolvedRef] = db.get_all_tables()

        # If table_name is specified, extract all matching table_refs and check if any exist
        resolved_input_table_refs: list[ResolvedRef] = []
        if table_name is not None:
            parsed_input: InputRef = db.parse_input_ref(table_name, schema_name)

            if parsed_input.schema_name is not None and parsed_input.schema_name not in schema_names:
                raise DBpeekError(f"Schema '{parsed_input.schema_name}' not found")
            
            resolved_input_table_refs: list[ResolvedRef] = db.resolve_table_ref(parsed_input)

            if len(resolved_input_table_refs) == 0:
                raise DBpeekError(f"Table '{table_name}' not found")
            
        # If no table_name is provided, get all tbales of provided schema. If schema not provided as well then all tables are extracted.
        else:
            resolved_input_table_refs = db.get_all_tables(schema=schema_name)

     # Get table info for all tables and determine/save their relations to one another
    all_table_rels: list[tuple[ResolvedRef,list[ResolvedRef]]] = []
   
    with handle_cli_errors(f"Failed to extract table infos to build relational view"):
        for reference in all_table_refs:
            info: TableInfo = db.get_table_info(reference) 

            referred_tables: list[ResolvedRef] = []
            for referral in info.fk:
                target_name = referral["referred_table"]
                target_schema = referral.get("referred_schema")

                # If database does not return a referred schema field, try to resolve the table name manually
                if target_schema is None:
                    input_ref = InputRef(name=target_name)
                    resolved_ref = db.resolve_table_ref(input_ref)
                    if len(resolved_ref) != 1:
                        raise DBpeekError(f"Failed to extract schema for table '{target_name}' while building relational view")
                    target_schema = resolved_ref[0].schema_name

                target_ref = ResolvedRef(name=target_name, schema_name=target_schema)
                referred_tables.append(target_ref)

            # Build adjacency list of tables paired with tables they refer to
            all_table_rels.append((reference, referred_tables))

    # Build up relational tree (rich tree struct)
    relation_trees: list[RiTree] = []
    shown: set[tuple[str, str]] = set()

    if table_name is not None:
        roots = resolved_input_table_refs
    else:
        # Find roots within the selected schema, or across all tables if no schema was given.
        selected_keys = {(ref.schema_name, ref.name) for ref in resolved_input_table_refs}
        roots = [
            ref for ref, relations in all_table_rels
            if (ref.schema_name, ref.name) in selected_keys
            and not any((target.schema_name, target.name) in selected_keys for target in relations)
        ]

    for ref in roots:
        relation_trees.append(build_tree(ref, toggle_schema_output, all_table_rels, shown))

    # A relational component without a root (cycle) still needs one starting table.
    for ref in resolved_input_table_refs:
        if (ref.schema_name, ref.name) not in shown:
            relation_trees.append(
                build_tree(ref, toggle_schema_output, all_table_rels, shown)
            )

    # Print trees to console
    for tree in relation_trees:
        ri_console.print(tree)

    return


def build_tree(ref: ResolvedRef, toggle_schema: bool, all_table_rels: list[tuple[ResolvedRef,list[ResolvedRef]]],
               shown: set[tuple[str, str]]) -> RiTree:
    
    # Initiate new tree root either with schema name or without depending on the toggle
    tree = RiTree(ref.name) if toggle_schema else RiTree(f"{ref.schema_name}.{ref.name}")

    # Store visited refs in path to keep subtrees concise and to detect circular relations
    path: set[tuple[str, str]] = set() 
    
    # Search for referrences and append recursively to the tree root (in-place)
    append_to_tree(ref=ref, toggle_schema=toggle_schema, tree=tree, 
                    all_table_rels=all_table_rels, path=path, shown=shown)

    return tree


def append_to_tree(ref: ResolvedRef, toggle_schema: bool, tree: RiTree, all_table_rels: list[tuple[ResolvedRef,list[ResolvedRef]]], 
                   path: set[tuple[str, str]], shown: set[tuple[str, str]]) -> None:
    
    key = (ref.schema_name, ref.name)
    shown.add(key)
    current_path = path | {key}

    for child_ref, child_relations in all_table_rels:
        if ref not in child_relations:
            continue

        child_key = (child_ref.schema_name, child_ref.name)
        label = child_ref.name if toggle_schema else f"{child_ref.schema_name}.{child_ref.name}"

        if child_key in current_path:
            tree.add(f"{label} ↺ cycle")
            continue

        child = tree.add(label)
        append_to_tree(child_ref, toggle_schema, child, all_table_rels, current_path, shown)


@app.command()
def fks(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None,
        schema_name: Annotated[str, typer.Option("--schema", "-s")] = None,
        toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = get_db(ctx)

    with handle_cli_errors("Failed to extract schema names from db"):
        schema_names: list[str] = db.get_all_schema_names()
        if schema_name is not None and schema_name not in schema_names:
            raise DBpeekError(f"Schema '{schema_name}' not found.")

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

        tree = RiTree(table.name) if toggle_schema_output else RiTree(f"{table.schema_name}.{table.name}")

        if not table.fk:
            tree.add("null")
        else:
            for fk in table.fk:
                target = fk["referred_table"]
                target_schema = fk.get("referred_schema")
                if target_schema is not None and not toggle_schema_output:
                    target = f"{target_schema}.{target}"

                source_columns = fk["constrained_columns"]
                target_columns = fk.get("referred_columns") or []
                if len(source_columns) != len(target_columns):
                    target_columns = ["<unknown column>"] * len(source_columns)

                pairs = zip(source_columns, target_columns, strict=True)
                mappings = ", ".join(
                    f"{source} -> {target}.{column or '<unknown column>'}" for source, column in pairs
                )
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





         
