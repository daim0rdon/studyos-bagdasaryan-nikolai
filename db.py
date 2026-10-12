"""All SQLite connections and SQL access are centralized here."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('file', 'dir')),
    content TEXT NOT NULL DEFAULT '',
    owner_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_id, name)
);
CREATE TABLE IF NOT EXISTS processes (
    pid INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('running', 'stopped')),
    owner_id INTEGER NOT NULL REFERENCES users(id),
    memory_kb INTEGER NOT NULL CHECK (memory_kb > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    terminated_at TEXT
);
CREATE TABLE IF NOT EXISTS syscalls_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    status TEXT NOT NULL CHECK (status IN ('OK', 'ERROR', 'DENIED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS memory_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    used_kb INTEGER NOT NULL DEFAULT 0 CHECK (used_kb >= 0),
    limit_kb INTEGER NOT NULL CHECK (limit_kb > 0)
);
CREATE INDEX IF NOT EXISTS idx_files_parent ON files(parent_id);
CREATE INDEX IF NOT EXISTS idx_files_owner ON files(owner_id);
CREATE INDEX IF NOT EXISTS idx_process_owner ON processes(owner_id);
CREATE INDEX IF NOT EXISTS idx_log_user ON syscalls_log(user_id);
"""


class Database:
    """Expose a small SQL API without leaking SQLite into other modules."""

    def __init__(self, path="studyos.db", memory_limit_kb=1024):
        """Open the database, create the schema and initialize system dirs."""
        if path != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        with self.transaction():
            self.execute(
                "INSERT OR IGNORE INTO memory_state(id, used_kb, limit_kb) "
                "VALUES (1, 0, ?)", (memory_limit_kb,)
            )
            self.execute(
                "INSERT OR IGNORE INTO files(name, path, parent_id, kind) "
                "VALUES ('/', '/', NULL, 'dir')"
            )
            root = self.fetchone("SELECT id FROM files WHERE path = '/' ")
            self.execute(
                "INSERT OR IGNORE INTO files(name, path, parent_id, kind) "
                "VALUES ('home', '/home', ?, 'dir')", (root["id"],)
            )

    @contextmanager
    def transaction(self):
        """Commit a group of statements together, or roll back on error."""
        with self.connection:
            yield

    def execute(self, statement, params=()):
        """Execute a parameterized statement and return its cursor."""
        return self.connection.execute(statement, params)

    def fetchone(self, statement, params=()):
        """Return the first matching row as a dictionary, if present."""
        row = self.execute(statement, params).fetchone()
        return dict(row) if row is not None else None

    def fetchall(self, statement, params=()):
        """Return matching rows as dictionaries."""
        return [dict(row) for row in self.execute(statement, params).fetchall()]

    def scalar(self, statement, params=()):
        """Return the first column of the first row, or None."""
        row = self.execute(statement, params).fetchone()
        return row[0] if row is not None else None

    def close(self):
        """Close the database connection."""
        self.connection.close()
