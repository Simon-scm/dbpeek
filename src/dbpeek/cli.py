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
def info(ctx: typer.Context):
    db: DatabaseContext= ctx.obj
    inspector = db.inspector
    typer.echo("inspector created")
    typer.Exit(0)



