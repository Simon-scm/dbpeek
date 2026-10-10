import sqlite3
from pathlib import Path

DB_PATH = Path("test.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.executescript(
        """
        DROP TABLE IF EXISTS submissions;
        DROP TABLE IF EXISTS users;

        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            problem_name TEXT NOT NULL,
            language TEXT NOT NULL,
            accepted INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    users = [
        ("simon", "simon@example.com", "2026-10-01 10:00:00"),
        ("alice", "alice@example.com", "2026-10-02 12:30:00"),
        ("bob", "bob@example.com", "2026-10-03 09:15:00"),
    ]

    cursor.executemany(
        """
        INSERT INTO users (username, email, created_at)
        VALUES (?, ?, ?)
        """,
        users,
    )

    submissions = [
        (1, "Two Sum", "Python", 1, "2026-10-05 14:20:00"),
        (1, "Valid Parentheses", "Python", 1, "2026-10-05 15:10:00"),
        (1, "Merge Intervals", "Java", 0, "2026-10-06 11:00:00"),
        (2, "Two Sum", "JavaScript", 1, "2026-10-06 12:00:00"),
        (2, "Binary Search", "Python", 1, "2026-10-07 08:45:00"),
        (3, "Linked List Cycle", "Go", 1, "2026-10-07 18:30:00"),
    ]

    cursor.executemany(
        """
        INSERT INTO submissions (
            user_id,
            problem_name,
            language,
            accepted,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        submissions,
    )

    conn.commit()
    conn.close()

    print(f"Created and seeded SQLite database: {DB_PATH.resolve()}")


if __name__ == "__main__":
    main()