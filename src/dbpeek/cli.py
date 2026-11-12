from typing import Annotated
from sqlalchemy.exc import SQLAlchemyError
from .database import resolve_db_conn, DatabaseContext, TableInfo, InputRef, ResolvedRef
import typer
from rich.console import Console as RiConsole
from rich.table import Table as RiTable
from rich.text import Text
from rich.tree import Tree as RiTree

# TODO: 
# - Create real sqlite test db and pre define env variable??
# - All functions/commands need a header comment roughly explaining what the command does
# - Include schema handling in --help -> define "helps" for all commands


# Entrance point of the program 
app = typer.Typer(invoke_without_command=True)
ri_console = RiConsole()
ri_error_console = RiConsole(stderr=True)


# Function that runs everytime a command is called (also when the application gets run without any command)
@app.callback()
def main(ctx: typer.Context, url: Annotated[str | None, typer.Option("--url", "-u")] = None):
    try:
        # db connection will be set up
        db_conn: DatabaseContext = resolve_db_conn(url)
        ctx.obj = db_conn
        
    except (SQLAlchemyError, RuntimeError) as exc:
        ri_error_console.print(f"Database connection failed: {exc}", markup=False)
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
            ri_error_console.print(exc, markup=False)
            raise typer.Exit(code=1)
    else:
        # If no schema is provided in table_name and also not in the --schema option, the name will be searched in all schemas and all information will be returned
        # If --schema option is set everything in table_name will be interpreted as the pure tablename 
        input_ref: InputRef = db.parse_input_ref(input_name=table_name, input_schema=schema_name)
        try:
            resolved_refs: list[ResolvedRef] = db.resolve_table_ref(input_ref)
            if len(resolved_refs) == 0:
                raise Exception("Provided table does not exist")
            
            table_infos: list[TableInfo] = []
            for ref in resolved_refs:
                table_infos.append(db.get_table_info(ref))

            for info in table_infos:
                ri_console.print(info.model_dump_json(indent=2))
            return
        
        except Exception as exc:
            ri_error_console.print(exc, markup=False)
            raise typer.Exit(code=1)


@app.command()
def schemas(ctx: typer.Context):
    
    db: DatabaseContext = ctx.obj
    try:
        schema_names = db.get_all_schema_names()
        ri_console.print(schema_names)
        return
    
    except Exception as exc:
        ri_console.print(f"Failed to extract schema names from db: {exc}")
        raise typer.Exit(code=1)



@app.command()
def tables(ctx: typer.Context, 
           relation: Annotated[bool, typer.Option("--rel", "-r")] = False, 
           schema_name: Annotated[str | None, typer.Option("--schema", "-s")] = None,
           toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = ctx.obj
    
    try:
        schema_names: list[str] = db.get_all_schema_names()
    except Exception as exc:
        ri_console.print(f"Failed to extract schema names from db: {exc}")
        raise typer.Exit(code=1)
    
    if schema_name is not None and schema_name not in schema_names:
        ri_console.print(f"Schema '{schema_name}' is not defined in the db")
        raise typer.Exit(code=1)
    
    try:
        table_refs: list[ResolvedRef]= db.get_all_tables(schema=schema_name)
    except Exception as exc:
        ri_console.print(f"Failed to extract table references from db: {exc}")
        raise typer.Exit(code=1)

    
    if not relation:
        if toggle_schema_output:
            ri_console.print([ ref.name for ref in table_refs ])
        else:
            ri_console.print([ ref.schema_name + "." + ref.name for ref in table_refs ])
        return

    # TODO: Neue resolve Logik implementieren und Graph statt Tree erzeugen
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
        view_refs: list[ResolvedRef] = db.get_all_views(schema=schema_name)
    except Exception as exc:
        ri_console.print(f"Failed to extract view references from db: {exc}")
        raise typer.Exit(code=1)

    if toggle_schema_output:
        ri_console.print([ ref.name for ref in view_refs ])
    else:
        ri_console.print([ ref.schema_name + "." + ref.name for ref in view_refs ])
    return



@app.command()
def fks(ctx: typer.Context, table_name: Annotated[str, typer.Argument()] = None,
        schema_name: Annotated[str, typer.Option("--schema", "-s")] = None,
        toggle_schema_output: Annotated[bool, typer.Option("--shownoschema", "-sns")] = False):
    
    db: DatabaseContext = ctx.obj

    try:
        # If no table name is specified -> gets all tables of the specified schema, if no schema is speicified as well, all tables of all schemas are returned
        if table_name is None:
            resolved_refs: list[ResolvedRef] = db.get_all_tables(schema=schema_name)

            if len(resolved_refs) == 0:
                raise Exception("No tables found.")

        # If table is specified returns all tables references with the given name (out of all schemas) or one table reference if schema is specified as well
        else:
            input_ref: InputRef = db.parse_input_ref(input_name=table_name, input_schema=schema_name)
            resolved_refs: list[ResolvedRef]  = db.resolve_table_ref(input_ref=input_ref)

            if len(resolved_refs) == 0:
                raise Exception("Provided table does not exist.")
            
    except Exception as exc:
        ri_error_console.print(f"Failed to extract table references: {exc}", markup=False)
        raise typer.Exit(code=1)

    table_infos: list[TableInfo] = []
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

    db: DatabaseContext = ctx.obj
   
    input_ref: InputRef = db.parse_input_ref(input_name=name, input_schema=schema_name)
    try:
        resolved_ref: ResolvedRef = db.resolve_relation_ref(input_ref)
    except Exception as exc:
        ri_error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1)

    try:
        if all:
            rows: list = db.get_rows(resolved_ref)
        else:
            rows: list = db.get_rows(resolved_ref, row_count)

        if not rows:
            raise Exception(f"Failed to load rows of table/view: {resolved_ref.schema_name}.{resolved_ref.name}")
        
    except Exception as exc:
        ri_console.print(exc)
        raise typer.Exit(code=1)

    try:
        rich_table = RiTable(title=Text(f"{resolved_ref.schema_name}.{resolved_ref.name}"))
        for column_name in rows[0]:
            rich_table.add_column(Text(column_name))

        for row in rows[1:]:
            rich_table.add_row(
                *(Text("NULL" if value is None else str(value)) for value in row)
            )

        ri_console.print(rich_table)
        return

    except Exception as exc:
        ri_console.print(f"Failed to print rows of table/view '{resolved_ref.schema_name}.{resolved_ref.name}' to the terminal: {exc}")
        raise typer.Exit(code=1)


@app.command()
def count(ctx: typer.Context, name: Annotated[str, typer.Argument()], schema_name: Annotated[str, typer.Option("--schema", "-s")] = None):
    db: DatabaseContext = ctx.obj

    input_ref: InputRef = db.parse_input_ref(input_name=name, input_schema=schema_name)
    try:
        resolved_ref: ResolvedRef = db.resolve_relation_ref(input_ref)
    except Exception as exc:
        ri_error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1)
    
    try:
        row_count: int = db.get_row_count(resolved_ref)
        column_count: int = db.get_column_count(resolved_ref)

        ri_console.print(f"Table: {resolved_ref.schema_name}.{resolved_ref.name}")
        ri_console.print(f"Rows: {row_count}")
        ri_console.print(f"Columns: {column_count}")
        return

    except Exception as exc:
        ri_console.print(f"Failed to extract row and column count of table/view '{resolved_ref.schema_name}.{resolved_ref.name}': {exc}")
        raise typer.Exit(code=1)




         