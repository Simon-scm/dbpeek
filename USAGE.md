# dbpeek usage

Use `dbpeek` to inspect a database from the terminal. Start with `schemas`, `tables`, or `views` to find an object, then use `info`, `fks`, `rows`, or `count` to inspect it.

## Connecting

Follow the [README quick start](README.md#quick-start) to run from the repository root. The examples use `uv run python -m dbpeek` and assume an existing SQLite database with a `users` table, an `orders` table that references it, and an `active_users` view.

```text
uv run python -m dbpeek [GLOBAL OPTIONS] [COMMAND] [COMMAND OPTIONS]
```

Set `DBPEEK_DATABASE_URL` to a SQLAlchemy connection URL. If it is unset or the connection fails, dbpeek tries `DATABASE_URL`. An explicit `--url` takes precedence and is the only URL tried for that invocation. Place it before the command.

```powershell
uv run python -m dbpeek --url sqlite:///app.db tables
```

| Global option | Behavior |
| --- | --- |
| `--url URL`, `-u URL` | Use the given SQLAlchemy connection URL. |
| `--help` | Show global help. Use `<command> --help` for command-specific help. Help works without a database connection. |
| `--install-completion` | Install shell completion for the current shell. |
| `--show-completion` | Print the completion script for the current shell. |

Running without a command is equivalent to `info` without a table name.

## Selecting a schema

Use a qualified name such as `main.users` or pass the plain name with `--schema main`. Use one form per call. When `--schema` is set, dbpeek treats the whole positional argument as the object name, including any dots.

Without a schema, `info` and `fks` search all schemas for matching tables and show each match. `rows` and `count` search both tables and views and require exactly one match. If the name is ambiguous, they list the candidates and ask for a schema.

## Command reference

All commands support `--help`. In the syntax below, square brackets mark optional arguments or options.

### `info`

`info [TABLE] [--schema SCHEMA]`

Without a table argument, prints connection metadata as JSON, including the database type, driver, database name, and host when available. With a table argument, prints columns, primary and foreign keys, unique and check constraints, and indexes. One table is returned as a JSON object. Multiple matching tables are returned as a JSON array.

- `--schema SCHEMA`, `-s SCHEMA` limits the table lookup to that schema. It has no effect when no table is supplied.

```powershell
uv run python -m dbpeek info
uv run python -m dbpeek info main.users     <=>     uv run python -m dbpeek info users --schema main
```

### `schemas`

`schemas`

Lists the schemas visible to the database connection. It takes no arguments or command-specific options.

```powershell
uv run python -m dbpeek schemas
```

### `tables`

`tables [--schema SCHEMA] [--shownoschema] [--rel]`

Lists tables across all visible schemas by default. Names are displayed as `schema.table`.

- `--schema SCHEMA`, `-s SCHEMA` lists tables in one schema.
- `--shownoschema`, `-sns` displays names without schema prefixes.
- `--rel`, `-r` displays relationship trees. Each tree starts at a table without outgoing foreign keys and shows the tables that reference it. This view is experimental and can omit rootless cycles, parts of shared branches, and targets outside the selected schema. Use `fks` to inspect the declared keys directly.

```powershell
uv run python -m dbpeek tables --schema main
uv run python -m dbpeek tables --rel
```

### `views`

`views [--schema SCHEMA] [--shownoschema]`

Lists views across all visible schemas by default. Use `rows` or `count` to inspect a view's result.

- `--schema SCHEMA`, `-s SCHEMA` lists views in one schema.
- `--shownoschema`, `-sns` displays names without schema prefixes.

```powershell
uv run python -m dbpeek views --schema main --shownoschema
```

### `fks`

`fks [TABLE] [--schema SCHEMA] [--shownoschema]`

Shows outgoing foreign keys from each selected table. Each key maps source columns to the referenced table and columns. Composite keys are grouped together. Omit the table to inspect all tables in scope.

- `--schema SCHEMA`, `-s SCHEMA` limits the source tables to one schema.
- `--shownoschema`, `-sns` hides schema prefixes on source and target names.

```powershell
uv run python -m dbpeek fks main.orders
uv run python -m dbpeek fks --schema main
```

### `rows`

`rows NAME [--schema SCHEMA] [--count N] [--all]`

Previews rows from a single table or view. The default is 10 rows. Results have no guaranteed order.

- `--schema SCHEMA`, `-s SCHEMA` selects the schema.
- `--count N`, `-c N` sets the maximum number of rows. A value of `0` shows only column headers.
- `--all`, `-a` fetches every row and overrides `--count`.

```powershell
uv run python -m dbpeek rows users --schema main --count 5
uv run python -m dbpeek rows main.active_users --count 0
```

### `count`

`count NAME [--schema SCHEMA]`

Reports the number of columns and rows in a single table or view.

- `--schema SCHEMA`, `-s SCHEMA` selects the schema.

```powershell
uv run python -m dbpeek count main.active_users
```
