from sqlalchemy import create_engine, func, inspect, Engine, MetaData, select, Table, table
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
import os



class InputRef(BaseModel):
    name: str
    schema_name: str | None = None

class ResolvedRef(BaseModel):
    name: str
    schema_name: str

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

    # parses input table name like "main.users" into TableRef structure -> consisting of name and schema
    # function breaks done input_name at first "." everything before is schema everything behind is table name
    # if schema contains a "." it has to be provided as input_schema over --schema option in cli
    # then input_schema will not be None and will be set as schema
    def parse_input_ref(self, input_name: str, input_schema: str | None) -> InputRef:
        if input_schema is not None:
            return InputRef(name=input_name, schema_name=input_schema)

        if "." in input_name:
            parsed_schema, parsed_name = input_name.split(".", 1)
            return InputRef(name=parsed_name, schema_name=parsed_schema)

        return InputRef(name=input_name)
    
    
    # returns all references to tables that match the provided name and schema (if no schema is provided it returns all refs across all schemas that match the name)
    def resolve_table_ref(self, input_ref: InputRef) -> list[ResolvedRef]:
            table_refs: list[ResolvedRef] = []

            if input_ref.schema_name is None:
                all_schemas: list[str] = self.get_all_schema_names()
                for schema in all_schemas:
                    table_names = self.inspector.get_table_names(schema=schema)

                    if input_ref.name in table_names:
                        table_refs.append(ResolvedRef(name=input_ref.name, schema_name=schema))

            else:
                table_names =  self.inspector.get_table_names(schema=input_ref.schema_name)
                if input_ref.name in table_names:
                    table_refs.append(ResolvedRef(name=input_ref.name, schema_name=input_ref.schema_name))

            return table_refs
            

    # returns all references to views that match the provided name and schema (if no schema is provided it returns all refs across all schemas that match the name)
    def resolve_view_ref(self, input_ref: InputRef) -> list[ResolvedRef]:
        view_refs: list[ResolvedRef] = []

        if input_ref.schema_name is None:
            all_schemas: list[str] = self.get_all_schema_names()
            for schema in all_schemas:
                table_names = self.inspector.get_view_names(schema=schema)

                if input_ref.name in table_names:
                    view_refs.append(ResolvedRef(name=input_ref.name, schema_name=schema))

        else:
            table_names =  self.inspector.get_view_names(schema=input_ref.schema_name)
            if input_ref.name in table_names:
                view_refs.append(ResolvedRef(name=input_ref.name, schema_name=input_ref.schema_name))


        return view_refs

    # resolves and returns exactly one view or table (for commands that operate on exactly one reference which can be a table OR a view like "rows" or " count")  
    def resolve_relation_ref(self, requested: InputRef) -> ResolvedRef:
        schema = requested.schema_name
        if schema is not None and not self.inspector.has_schema(schema):
            raise ValueError(f"Schema '{schema}' not found.")

        matches = self.resolve_table_ref(requested) + self.resolve_view_ref(requested)

        if not matches:
            raise ValueError(f"Table or View '{requested.name}' not found.")

        if len(matches) > 1:
            names = ", ".join(f"{ref.schema_name}.{ref.name}" for ref in matches)
            raise ValueError(f"More than one relation found: {names}. Please specify a schema.")

        return matches[0]

    
    # TODO: implement DBMS specific schema filter to filter out system schema if not actively wanted !!!
    def get_all_schema_names(self) -> list[str]:
            return self.inspector.get_schema_names()


    # find all tables in entire db or of a specific schema
    def get_all_tables(self, schema:str | None = None) -> list[ResolvedRef]:
        if schema is not None:
            table_names: list[str] = self.inspector.get_table_names(schema=schema)
            table_refs: list[ResolvedRef] = [ResolvedRef(name=table_name, schema_name=schema) for table_name in table_names]
        else:
            all_schemas: list[str] = self.get_all_schema_names()
            table_refs: list[ResolvedRef] = []
            for schema in all_schemas:
                table_names= self.inspector.get_table_names(schema=schema)
                table_refs.extend([ ResolvedRef(name=table_name, schema_name=schema) for table_name in table_names ])

        return table_refs


    # find all views in entire db or of a specific schema
    def get_all_views(self, schema:str | None = None) -> list[ResolvedRef]:
        if schema is not None:
            view_names: list[str] = self.inspector.get_view_names(schema=schema)
            view_refs: list[ResolvedRef] = [ResolvedRef(name=view_name, schema_name=schema) for view_name in view_names]
        else:
            all_schemas: list[str] = self.get_all_schema_names()
            view_refs: list[ResolvedRef] = []
            for schema in all_schemas:
                view_names= self.inspector.get_view_names(schema=schema)
                view_refs.extend([ ResolvedRef(name=view_name, schema_name=schema) for view_name in view_names ])

        return view_refs

            
    # returns info of a specific table 
    def get_table_info(self, table_ref: ResolvedRef) -> TableInfo:

        raw_columns = self.inspector.get_columns(table_ref.name, table_ref.schema_name)

        # to convert the sqlalchemy typ object into text ("INTEGER")
        cleaned_columns = []
        for col in raw_columns:
            col_copy = col.copy()
            col_copy['type'] = str(col['type'])
            cleaned_columns.append(col_copy)

        table_info = TableInfo(
            name=table_ref.name,
            schema_name=table_ref.schema_name,
            columns=cleaned_columns,
            pk=self.inspector.get_pk_constraint(table_ref.name, table_ref.schema_name),
            fk=self.inspector.get_foreign_keys(table_ref.name, table_ref.schema_name),
            idx=self.inspector.get_indexes(table_ref.name, table_ref.schema_name),
        )

        return table_info


    def get_rows(self, ref: ResolvedRef, row_count: int | None = None) -> list:
        if row_count is not None and row_count < 0:
            raise ValueError("Row count must be non-negative")

        with self.engine.connect() as conn:
            target = Table(
                ref.name, MetaData(), schema=ref.schema_name,
                autoload_with=conn, resolve_fks=False,
            )
            statement = select(target)
            if row_count is not None:
                statement = statement.limit(row_count)

            result = conn.execute(statement)
            columns = list(result.keys())
            return [columns, *result.fetchall()]


    def get_row_count(self, ref: ResolvedRef) -> int:
        target = table(ref.name, schema=ref.schema_name)
        statement = select(func.count()).select_from(target)
        with self.engine.connect() as conn:
            return conn.execute(statement).scalar_one()


    def get_column_count(self, ref: ResolvedRef) -> int:
        return len(self.inspector.get_columns(table_name=ref.name, schema=ref.schema_name))


    def is_table(self, ref: ResolvedRef) -> bool:
         table_names = self.inspector.get_table_names(schema=ref.schema_name)

         return True if ref.name in table_names else False

    def is_view(self, ref: ResolvedRef) -> bool:
        view_names = self.inspector.get_view_names(schema=ref.schema_name)
                 
        return True if ref.name in view_names else False
   




# if engine.connect() errors the error will propagate and this specific connection url is dismissed
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
            inspector = inspect(engine)
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




