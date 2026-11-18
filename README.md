# dbpeek

`dbpeek` is a lightweight CLI for inspecting databases during development. Browse schemas, trace foreign keys, and preview data from the terminal without writing SQL.

[GitHub repository](https://github.com/Simon-scm/dbpeek)

## Quick start

`dbpeek` requires Python 3.13 or newer. Install the package from PyPI with uv:

```powershell
uv tool install dbpeek
```

Use `dbpeek` or its shorter alias `dbpk`. For example, run these commands against an existing SQLite database named `app.db` (with a `users` table):

```powershell
dbpeek --url sqlite:///app.db tables
dbpeek --url sqlite:///app.db info users
dbpk --url sqlite:///app.db rows users --count 5
```

To reuse a connection, set the environment variable `DBPEEK_DATABASE_URL` to the connection string of your db. If it is unset or the connection fails, `dbpeek` tries `DATABASE_URL`. Using the explicit `--url` flag takes precedence. Feature support depends on the database dialect.

## Commands

| Command | What it shows |
| --- | --- |
| `info` | Connection details as JSON |
| `info <table>` | Columns, keys, constraints, and indexes as JSON |
| `schemas`, `tables`, `views` | Available schemas, tables, and views |
| `relations [table]` | Trees of tables that reference the selected table or tables |
| `fks [table]` | Foreign keys and their target columns |
| `rows <name>` | A preview of a table or view, limited to 10 rows by default |
| `count <name>` | Row and column counts for a table or view |

Use `schema.name` or `name --schema schema_name` to select a schema when names overlap. See the [usage guide](https://github.com/Simon-scm/dbpeek/blob/main/USAGE.md) for all commands and options.

## Local development

Clone the repository and run the CLI from the checkout with uv:

```powershell
git clone https://github.com/Simon-scm/dbpeek.git
cd dbpeek
uv sync
uv run dbpeek --help
uv run pytest -q
```

## License

Released under the [MIT License](https://github.com/Simon-scm/dbpeek/blob/main/LICENSE.md).
