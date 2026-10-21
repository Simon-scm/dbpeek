from sqlalchemy import create_engine, inspect, Engine, MetaData, select, Table
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
import os



class TableRef(BaseModel):
    name: str
    schema_name: str | None = None

class TableInfo(BaseModel):
    name: str
    schema_name: str | None
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


    def parse_table_ref(self, input_name: str, input_schema: str | None) -> TableRef:
        if input_schema is not None:
            return TableRef(name=input_name, schema_name=input_schema)

        if "." in input_name:
            parsed_schema, parsed_name = input_name.split(".", 1)
            return TableRef(name=parsed_name, schema_name=parsed_schema)

        return TableRef(name=input_name)
    
    
    # returns all table names including their schema or only table names (+schema) of a specific schema
    def get_table_refs(self, schema_name: str | None = None) -> list[TableRef]:
            table_refs: list[TableRef] = []

            if not schema_name:
                all_schemas: list[str] = self.get_schema_names()
                for schema in all_schemas:
                    table_names = self.inspector.get_table_names(schema=schema)
                    table_refs.extend([TableRef(name=table_name, schema_name=schema) for table_name in table_names])

            else:
                table_names =  self.inspector.get_table_names(schema=schema_name)
                table_refs = [TableRef(name=table_name, schema_name=schema_name) for table_name in table_names]

            return table_refs

    
    # TODO: implement DBMS specific schema filter to filter out system schema if not actively wanted !!!
    def get_schema_names(self) -> list[str]:
            return self.inspector.get_schema_names()


    # finds all schemas that have a table with a specific name
    def get_table_schemas(self, table_name: str) -> list[str]:
        all_schemas: list[str] = self.get_schema_names()

        matches: list[str] = []

        for schema_name in all_schemas:
            table_refs = self.get_table_refs(schema_name=schema_name)

            if table_name in [ref.name for ref in table_refs]:
                matches.append(schema_name)

        return matches
            

    # if no schema is set in table reference, func returns basic information about all tables with the specified name (potentially from different schemas)
    # if schema is set func returns only info about the specific table reference
    def get_table_info(self, table_ref: TableRef) -> list[TableInfo]:

        table_schemas: list[str] = self.get_table_schemas(table_name=table_ref.name)

        if not table_schemas:
            raise Exception(f"Failed to find table '{table_ref.name}' in database")

        if table_ref.schema_name is not None:
            table_schemas = [table_ref.schema_name]

        table_infos: list[TableInfo] = []
        for schema in table_schemas:
            raw_columns = self.inspector.get_columns(table_ref.name, schema)

            # to convert the sqlalchemy typ object into text ("INTEGER")
            cleaned_columns = []
            for col in raw_columns:
                col_copy = col.copy()
                col_copy['type'] = str(col['type'])
                cleaned_columns.append(col_copy)

            table_infos.append(TableInfo(
                name=table_ref.name,
                schema_name=schema,
                columns=cleaned_columns,
                pk=self.inspector.get_pk_constraint(table_ref.name, schema),
                fk=self.inspector.get_foreign_keys(table_ref.name, schema),
                idx=self.inspector.get_indexes(table_ref.name, schema),
            ))

        return table_infos

    def get_rows(self, tabler_ref: TableRef, row_count: int | None = None) -> list:
        curr_table = Table(name=tabler_ref.name, metadata=MetaData(), schema=tabler_ref.schema_name, autoload_with=self.engine) 
    
        with self.engine.connect() as conn:
            rows = conn.execute(statement=select(curr_table))

        res = [rows._metadata.keys._keys]

        i = 0
        for row in rows:
            if row_count is not None and i >= row_count:
                break
            res.append(row)
            i+=1

        return res


    def get_row_count(self, table_ref: TableRef) -> int:
        return len(self.get_rows(table_ref=table_ref, row_count=-1)) - 1


    def get_column_count(self, table_ref: TableRef) -> int:
        return len(self.inspector.get_columns(table_name=table_ref.name, schema=table_ref.schema_name))

    
   




# if engine.connect() errors the error will propagate 
# TODO: time out einbauen - wenn localhost versucht wird und dieser nicht up ist, startet ein endless try (vermutlich)
# TODO: Überprüfen warum keine login Informationen nötig waren auf localhost
def try_create_engine(url: str) -> Engine:
    engine = create_engine(url)

    with engine.connect():
        pass

    return engine


def resolve_db_conn(cli_url: str | None = None) -> DatabaseContext:
    # if user provides a url as a cmd line argument we only try to connect to this address
    if cli_url is not None:
        candidates = [cli_url]
    # if no url is directly provided two env variables are checked
    else:
        candidates = [os.getenv("DBPEEK_DATABASE_URL"), os.getenv("DATABASE_URL")]

    last_error: SQLAlchemyError | None = None

    # for every possible url we try to create a valid db connection (engine)
    # as soon as we successfully crate a connection we return the engine and inspector as DatabasContext
    for url in candidates:
        if not url:
            continue

        try:
            engine = try_create_engine(url)
            inspector = get_inspector(engine)
            return DatabaseContext(engine=engine, inspector=inspector) 

        # if db engine creation fails the error is saved in a var
        # but no error is triggered yet, in case a valid url exitsts after the faulty one
        except SQLAlchemyError as exc:
            last_error = exc

    # if no valid engine has been created we raise the last error
    if last_error:
        raise last_error
    # if no valid engine was created and no error was occured -> there was no url provided at all
    raise RuntimeError("No database URL configured")


def get_inspector(engine: Engine):
        return inspect(engine)



