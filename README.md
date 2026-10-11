# dbpeek

`dbpeek` is a lightweight command-line tool for quickly inspecting the structure and current state of a database during development.

The idea behind is to provide a fast alternative to opening a full database GUI whenever you only want to answer simple questions such as:

- Which tables exist?
- How are tables related?
- What columns and constraints does a table contain?
- What data is currently stored in a table?
- Which database am I connected to?

The tool is intended to work directly from the terminal and to provide concise, readable output for common database inspection tasks.

The tool is built on SQLAlchemy's database abstraction and is designed to work across SQLAlchemy-supported database systems. Compatibility may vary depending on the capabilities of the underlying dialect.