import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from app.core.config import settings


def ensure_db_initialized() -> None:
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                token_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT,
                deleted_at TEXT
            );
            """
        )

        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at);")
        except sqlite3.OperationalError:
            pass

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
        _try_add_column(conn, "jobs", "eta_seconds INTEGER")
        _try_add_column(conn, "jobs", "speed_bps INTEGER")
        _try_add_column(conn, "jobs", "playlist_total INTEGER")
        _try_add_column(conn, "jobs", "playlist_succeeded INTEGER")
        _try_add_column(conn, "jobs", "playlist_failed INTEGER")


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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_user_id, created_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_logs(target_type, target_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);")
        except sqlite3.OperationalError:
            pass

        conn.commit()
    finally:
        conn.close()


def _try_add_column(conn: sqlite3.Connection, table: str, col_def: str) -> None:
    # col_def example: "output_filename TEXT"
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def};")
    except sqlite3.OperationalError:
        # most likely "duplicate column name"
        pass


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
