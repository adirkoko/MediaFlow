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

        _ensure_quota_tables(conn)
        _ensure_usage_tables(conn)
        _ensure_login_attempts_table(conn)

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


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_quota_tables(conn: sqlite3.Connection) -> None:
    quota_columns = """
        role TEXT PRIMARY KEY,
        max_active_jobs INTEGER NOT NULL,
        max_jobs_per_day INTEGER NOT NULL,
        max_jobs_per_week INTEGER NOT NULL,
        max_jobs_per_month INTEGER NOT NULL,
        max_credits_per_day INTEGER NOT NULL,
        max_credits_per_week INTEGER NOT NULL,
        max_credits_per_month INTEGER NOT NULL,
        max_playlist_items_per_job INTEGER NOT NULL,
        max_playlist_items_per_day INTEGER NOT NULL,
        max_video_duration_seconds INTEGER,
        max_video_quality TEXT NOT NULL,
        max_output_mb_per_day INTEGER,
        max_output_mb_per_month INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    """
    conn.execute(f"CREATE TABLE IF NOT EXISTS role_quotas ({quota_columns});")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_quotas (
            user_id TEXT PRIMARY KEY,
            max_active_jobs INTEGER,
            max_jobs_per_day INTEGER,
            max_jobs_per_week INTEGER,
            max_jobs_per_month INTEGER,
            max_credits_per_day INTEGER,
            max_credits_per_week INTEGER,
            max_credits_per_month INTEGER,
            max_playlist_items_per_job INTEGER,
            max_playlist_items_per_day INTEGER,
            max_video_duration_seconds INTEGER,
            max_video_quality TEXT,
            max_output_mb_per_day INTEGER,
            max_output_mb_per_month INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    now_expr = "datetime('now')"
    conn.execute(
        f"""
        INSERT OR IGNORE INTO role_quotas (
            role, max_active_jobs, max_jobs_per_day, max_jobs_per_week,
            max_jobs_per_month, max_credits_per_day, max_credits_per_week,
            max_credits_per_month, max_playlist_items_per_job,
            max_playlist_items_per_day, max_video_duration_seconds,
            max_video_quality, max_output_mb_per_day, max_output_mb_per_month,
            created_at, updated_at
        )
        VALUES (
            'user',
            {settings.max_active_jobs_per_user},
            50, 250, 1000, 200, 1000, 4000,
            50, 200, 7200, '1080p', NULL, NULL,
            {now_expr}, {now_expr}
        );
        """
    )
    conn.execute(
        f"""
        INSERT OR IGNORE INTO role_quotas (
            role, max_active_jobs, max_jobs_per_day, max_jobs_per_week,
            max_jobs_per_month, max_credits_per_day, max_credits_per_week,
            max_credits_per_month, max_playlist_items_per_job,
            max_playlist_items_per_day, max_video_duration_seconds,
            max_video_quality, max_output_mb_per_day, max_output_mb_per_month,
            created_at, updated_at
        )
        VALUES (
            'admin',
            10, 500, 2500, 10000, 2000, 10000, 40000,
            200, 1000, 14400, '2160p', NULL, NULL,
            {now_expr}, {now_expr}
        );
        """
    )


def _ensure_usage_tables(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "usage_events")
    if columns and ("event_type" not in columns or "user_id" not in columns):
        conn.execute("ALTER TABLE usage_events RENAME TO usage_events_legacy;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            job_id TEXT,
            event_type TEXT NOT NULL,
            mode TEXT,
            quality TEXT,
            is_playlist INTEGER,
            playlist_items_requested INTEGER,
            playlist_items_succeeded INTEGER,
            playlist_items_failed INTEGER,
            requested_url_hash TEXT,
            estimated_credits INTEGER,
            actual_credits INTEGER,
            processing_time_ms INTEGER,
            duration_seconds INTEGER,
            output_size_bytes INTEGER,
            status TEXT,
            error_code TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_usage_daily (
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            jobs_requested INTEGER NOT NULL DEFAULT 0,
            jobs_started INTEGER NOT NULL DEFAULT 0,
            jobs_succeeded INTEGER NOT NULL DEFAULT 0,
            jobs_failed INTEGER NOT NULL DEFAULT 0,
            jobs_canceled INTEGER NOT NULL DEFAULT 0,
            audio_jobs INTEGER NOT NULL DEFAULT 0,
            video_jobs INTEGER NOT NULL DEFAULT 0,
            playlist_jobs INTEGER NOT NULL DEFAULT 0,
            credits_estimated INTEGER NOT NULL DEFAULT 0,
            credits_used INTEGER NOT NULL DEFAULT 0,
            total_processing_ms INTEGER NOT NULL DEFAULT 0,
            avg_processing_ms INTEGER NOT NULL DEFAULT 0,
            total_output_bytes INTEGER NOT NULL DEFAULT 0,
            playlist_items_requested INTEGER NOT NULL DEFAULT 0,
            playlist_items_succeeded INTEGER NOT NULL DEFAULT 0,
            playlist_items_failed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, date)
        );
        """
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_user_created ON usage_events(user_id, created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_job ON usage_events(job_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_type_created ON usage_events(event_type, created_at);")
    except sqlite3.OperationalError:
        pass


def _ensure_login_attempts_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            id TEXT PRIMARY KEY,
            username TEXT,
            user_id TEXT,
            ip_hash TEXT,
            user_agent TEXT,
            success INTEGER NOT NULL,
            failure_reason TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_username_created ON login_attempts(username, created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_created ON login_attempts(ip_hash, created_at);")
    except sqlite3.OperationalError:
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
