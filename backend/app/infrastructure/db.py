import sqlite3
from pathlib import Path

from app.core.config import settings


def ensure_db_initialized() -> None:
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                user TEXT NOT NULL,
                url TEXT NOT NULL,
                mode TEXT NOT NULL,
                quality TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error_message TEXT
            );
            """
        )

        # Lightweight migrations (ADD COLUMN if missing)
        _try_add_column(conn, "jobs", "output_filename TEXT")
        _try_add_column(conn, "jobs", "output_type TEXT")
        _try_add_column(conn, "jobs", "error_code TEXT")
        _try_add_column(conn, "jobs", "request_fingerprint TEXT")
        _try_add_column(conn, "jobs", "progress_percent INTEGER")
        _try_add_column(conn, "jobs", "stage TEXT")
        _try_add_column(conn, "jobs", "updated_at TEXT")

        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user, created_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user, status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(user, request_fingerprint, status);")
        except sqlite3.OperationalError:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                mode TEXT NOT NULL,
                is_playlist INTEGER NOT NULL,
                duration_ms INTEGER,
                success INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        conn.commit()


def _try_add_column(conn: sqlite3.Connection, table: str, col_def: str) -> None:
    # col_def example: "output_filename TEXT"
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def};")
    except sqlite3.OperationalError:
        # most likely "duplicate column name"
        pass


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
