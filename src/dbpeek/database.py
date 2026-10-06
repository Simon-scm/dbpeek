from sqlalchemy import create_engine, inspect, Engine
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import SQLAlchemyError
from dataclasses import dataclass
import os


@dataclass
class DatabaseContext:
    engine: Engine
    inspector: Inspector
     

def try_create_engine(url: str) -> Engine:
    engine = create_engine(url)

    with engine.connect():
        pass

    return engine


def resolve_db_conn(cli_url: str | None = None) -> DatabaseContext:
    
    if cli_url:
        candidates = [cli_url]
    else:
        candidates = [os.getenv("DBPEEK_DATABASE_URL"), os.getenv("DATABASE_URL")]

    last_error: SQLAlchemyError | None = None

    for url in candidates:
        if not url:
            continue

        try:
            engine = try_create_engine(url)
            inspector = get_inspector(engine)
            return DatabaseContext(engine=engine, inspector=inspector) 
        except SQLAlchemyError as exc:
            last_error = exc

    if last_error:
        raise last_error

    raise RuntimeError("No database URL configured")


def get_inspector(engine: Engine):
        return inspect(engine)