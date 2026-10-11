import sqlite3
from pathlib import Path

DB_PATH = Path("relationship_test.db")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS product_categories;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS addresses;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS departments;

CREATE TABLE departments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    department_id INTEGER,
    manager_id INTEGER,
    name TEXT NOT NULL,

    FOREIGN KEY (department_id)
        REFERENCES departments(id),

    FOREIGN KEY (manager_id)
        REFERENCES employees(id)
);

CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    account_manager_id INTEGER,
    name TEXT NOT NULL,

    FOREIGN KEY (account_manager_id)
        REFERENCES employees(id)
);

CREATE TABLE addresses (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    city TEXT NOT NULL,

    FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL
);

CREATE TABLE product_categories (
    product_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,

    PRIMARY KEY (product_id, category_id),

    FOREIGN KEY (product_id)
        REFERENCES products(id),

    FOREIGN KEY (category_id)
        REFERENCES categories(id)
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    shipping_address_id INTEGER NOT NULL,
    created_by_employee_id INTEGER,
    status TEXT NOT NULL,

    FOREIGN KEY (customer_id)
        REFERENCES customers(id),

    FOREIGN KEY (shipping_address_id)
        REFERENCES addresses(id),

    FOREIGN KEY (created_by_employee_id)
        REFERENCES employees(id)
);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,

    FOREIGN KEY (order_id)
        REFERENCES orders(id),

    FOREIGN KEY (product_id)
        REFERENCES products(id)
);
"""


SEED_SQL = """
INSERT INTO departments VALUES
(1, 'Sales'),
(2, 'IT');

INSERT INTO employees VALUES
(1, 1, NULL, 'Alice'),
(2, 1, 1, 'Bob'),
(3, 2, NULL, 'Charlie');

INSERT INTO customers VALUES
(1, 2, 'Acme Corp'),
(2, 1, 'Globex');

INSERT INTO addresses VALUES
(1, 1, 'Berlin'),
(2, 1, 'Hamburg'),
(3, 2, 'Cologne');

INSERT INTO categories VALUES
(1, 'Hardware'),
(2, 'Accessories');

INSERT INTO products VALUES
(1, 'Keyboard', 79.99),
(2, 'Mouse', 39.99),
(3, 'Monitor', 249.99);

INSERT INTO product_categories VALUES
(1, 1),
(1, 2),
(2, 2),
(3, 1);

INSERT INTO orders VALUES
(1, 1, 1, 2, 'open'),
(2, 2, 3, 1, 'shipped');

INSERT INTO order_items VALUES
(1, 1, 1, 2),
(2, 1, 2, 1),
(3, 2, 3, 2);
"""


def create_database() -> None:
    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_SQL)
        connection.executescript(SEED_SQL)
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    create_database()

    print(f"Database created: {DB_PATH.resolve()}")
    print("SQLAlchemy URL:")
    print(f"sqlite:///{DB_PATH.resolve().as_posix()}")


if __name__ == "__main__":
    main()