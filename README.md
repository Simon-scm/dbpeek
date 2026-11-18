# dbpeek

`dbpeek` is a lightweight CLI for inspecting databases during development. Use it to check a schema, trace a foreign key, get info about table properties or preview stored data straight from the terminal without writing SQL or having to open up a full GUI .

| Command | What it shows |
| --- | --- |
| `info` | Connection details as JSON |
| `info <table>` | Columns, keys, constraints, and indexes as JSON |
| `schemas`, `tables`, `views` | Available schemas, tables, and views |
| `relations <table>` | Recursive analysis of relation of all, some or a specific table |
| `fks [table]` | Foreign keys and their target columns |
| `rows <name>` | A preview of a table or view, limited to 10 rows by default |
| `count <name>` | Row and column counts for a table or view |

Use `schema.name` or `name --schema schema_name` to select a schema when names overlap.
Checkk out the [USAGE guide](USAGE.md#dbpeek-usage) for more detailed information.

## Quick start

From the repository root, with Python 3.13+ and uv installed, run these PowerShell commands against an existing SQLite database:

```powershell
uv sync
$env:PYTHONPATH = "src"
$env:DBPEEK_DATABASE_URL = "sqlite:///app.db"
uv run python -m dbpeek tables
uv run python -m dbpeek rows users --count 5
```

Set `DBPEEK_DATABASE_URL` to your SQLAlchemy connection URL. You can also pass `--url` before the command or use `DATABASE_URL` as a fallback. Feature support depends on the database dialect.

## License

Released under the [MIT License](LICENSE.md).
