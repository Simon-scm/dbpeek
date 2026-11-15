ATTACH DATABASE ':memory:' AS archive;
ATTACH DATABASE ':memory:' AS cycles;
ATTACH DATABASE ':memory:' AS empty;
PRAGMA foreign_keys = ON;

CREATE TABLE main.users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '[red]Bob[/red]',
    CONSTRAINT users_name_unique UNIQUE (name),
    CONSTRAINT users_name_check CHECK (length(name) > 0)
);
INSERT INTO main.users (id, name) VALUES (1, 'Alice'), (2, '[red]Bob[/red]');
CREATE TABLE archive.users (id INTEGER PRIMARY KEY, archived_name TEXT);
INSERT INTO archive.users VALUES (42, 'ArchiveOnly');

CREATE TABLE main.submissions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id)
);
CREATE VIEW main.empty_preview AS SELECT * FROM submissions;
CREATE VIEW main.preview AS SELECT name AS "[blue]name[/blue]" FROM users WHERE id = 2;
CREATE TABLE archive.preview (id INTEGER);
INSERT INTO archive.preview VALUES (99);
CREATE TABLE archive.only_archive (id INTEGER);
INSERT INTO archive.only_archive VALUES (42);

CREATE TABLE main.parent (a INTEGER, b INTEGER, PRIMARY KEY (a, b));
CREATE TABLE main.child (
    x INTEGER,
    y INTEGER,
    CONSTRAINT parent_key FOREIGN KEY (x, y) REFERENCES parent (a, b)
);
CREATE TABLE main.implicit_child (x INTEGER, y INTEGER, FOREIGN KEY (x, y) REFERENCES parent);
CREATE TABLE main.orphan (parent_id INTEGER REFERENCES missing_parent);

CREATE TABLE main.root_left (id INTEGER PRIMARY KEY);
CREATE TABLE main.root_right (id INTEGER PRIMARY KEY);
CREATE TABLE main.branch (
    id INTEGER PRIMARY KEY,
    left_id INTEGER REFERENCES root_left(id),
    right_id INTEGER REFERENCES root_right(id)
);
CREATE TABLE main.leaf (branch_id INTEGER REFERENCES branch(id));

CREATE TABLE cycles.cycle_a (id INTEGER PRIMARY KEY, b_id INTEGER REFERENCES cycle_b(id));
CREATE TABLE cycles.cycle_b (id INTEGER PRIMARY KEY, a_id INTEGER REFERENCES cycle_a(id));
CREATE TABLE cycles.employee (id INTEGER PRIMARY KEY, manager_id INTEGER REFERENCES employee(id));
