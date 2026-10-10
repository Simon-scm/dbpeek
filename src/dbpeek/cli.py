from typing import Annotated
from sqlalchemy.exc import SQLAlchemyError
from .database import resolve_db_conn, DatabaseContext
import typer



app = typer.Typer(invoke_without_command=True)


@app.callback()
def main(ctx: typer.Context, url: Annotated[str | None, typer.Option("--url", "-u")] = None):
    try:
        db_conn: DatabaseContext = resolve_db_conn(url)
        ctx.obj = db_conn
        
    except (SQLAlchemyError, RuntimeError) as exc:
        typer.echo(
            f"Database connection failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=1)

    if ctx.invoked_subcommand is None:
        info(ctx)



@app.command()
def tables(ctx: typer.Context, relation: Annotated[bool, typer.Option("--rel", "-r")] = False):
    db: DatabaseContext = ctx.obj
    tables = db.get_tables()
    typer.echo(tables)


@app.command()
def views(ctx: typer.Context):
    db: DatabaseContext = ctx.obj
    insp = db.inspector
    typer.echo(insp.get_view_names())


@app.command()
def info(ctx: typer.Context, table: Annotated[str, typer.Argument()] = None):
    db: DatabaseContext = ctx.obj
    if table is None:
        try:
            metadata = db.get_db_metadata()
            typer.echo(metadata.model_dump_json(indent=2))
        except Exception as exc:
            print(exc)
    else:
        try:
            table_info = db.get_table_info(table)
            typer.echo(table_info.model_dump_json(indent=2))
        except Exception as exc:
            print(exc)


@app.command()
def rows(
    ctx: typer.Context, 
    table: Annotated[str, typer.Argument()], 
    row_count: Annotated[int, typer.Option("--rows", "-r")] = 20):
    db: DatabaseContext = ctx.obj

    rows = db.get_rows(table, row_count)
    for row in rows:
        typer.echo(row)



