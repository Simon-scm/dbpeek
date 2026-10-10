from sqlalchemy import create_engine, inspect, Engine, MetaData, select, Table
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
import os



class TableInfo(BaseModel):
    name: str
    columns: list
    pk: dict
    fk: list
    idx: list

class DBMetadata(BaseModel):
    dbms: str
    driver: str
    database: str | None
    host: str | None
    port: int | None
    username: str | None


class DatabaseContext:
    def __init__(self, engine, inspector):
        self.engine: Engine = engine
        self.inspector: Inspector = inspector

    def get_db_metadata(self) -> DBMetadata:
        return DBMetadata(
            dbms=self.engine.dialect.name,
            driver=self.engine.dialect.driver,
            database=self.engine.url.database,
            host=self.engine.url.host,
            port=self.engine.url.port,
            username=self.engine.url.username,
        )
        

    def get_table_info(self, table_name: str) -> TableInfo:
        raw_columns = self.inspector.get_columns(table_name)
    
        # Konvertiert das SQLAlchemy-Typ-Objekt in einen Text (z.B. "INTEGER")
        cleaned_columns = []
        for col in raw_columns:
            col_copy = col.copy()
            col_copy['type'] = str(col['type'])
            cleaned_columns.append(col_copy)

        return TableInfo(
            name=table_name,
            columns=cleaned_columns,
            pk=self.inspector.get_pk_constraint(table_name),
            fk=self.inspector.get_foreign_keys(table_name),
            idx=self.inspector.get_indexes(table_name),
        )

    def get_rows(self, table_name: str, row_count: int):
        curr_table = Table(table_name, MetaData(), autoload_with=self.engine) 

        with self.engine.connect() as conn:
            rows = conn.execute(statement=select(curr_table))

        res = [rows._metadata.keys._keys]

        i = 1
        for row in rows:
            res.append(row)
            if i >= row_count:
                break
            i += 1

        return res

    def get_tables(self):
        return self.inspector.get_table_names()




def try_create_engine(url: str) -> Engine:
    engine = create_engine(url)

    with engine.connect():
        pass

    return engine


def resolve_db_conn(cli_url: str | None = None) -> DatabaseContext:
    if cli_url is not None:
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



