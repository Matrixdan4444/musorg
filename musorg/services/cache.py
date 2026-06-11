import json
import os
import sqlite3
import threading
from pathlib import Path


_CACHE_MISS = object()
_THREAD_LOCAL = threading.local()
_INIT_LOCK = threading.Lock()


def cache_db_path() -> Path:
    configured_path = (os.environ.get("MUSORG_CACHE_DB") or "").strip()
    if configured_path:
        return Path(configured_path).expanduser()

    if os.name == "posix" and "darwin" in os.sys.platform:
        return Path.home() / "Library" / "Caches" / "musorg" / "cache.sqlite3"

    xdg_cache_home = (os.environ.get("XDG_CACHE_HOME") or "").strip()
    if xdg_cache_home:
        return Path(xdg_cache_home).expanduser() / "musorg" / "cache.sqlite3"

    return Path.home() / ".cache" / "musorg" / "cache.sqlite3"


def _initialize_connection(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata_cache (
            namespace TEXT NOT NULL,
            cache_key TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (namespace, cache_key)
        )
        """
    )


def _connect() -> sqlite3.Connection:
    connection = getattr(_THREAD_LOCAL, "connection", None)
    db_path = getattr(_THREAD_LOCAL, "db_path", None)
    current_db_path = str(cache_db_path())

    if connection is not None and db_path == current_db_path:
        return connection

    db_path = cache_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    with _INIT_LOCK:
        _initialize_connection(connection)
    _THREAD_LOCAL.connection = connection
    _THREAD_LOCAL.db_path = str(db_path)
    return connection


def serialize_cache_key(parts) -> str:
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def cache_get(namespace: str, cache_key: str):
    connection = _connect()
    row = connection.execute(
        "SELECT payload FROM metadata_cache WHERE namespace = ? AND cache_key = ?",
        (namespace, cache_key),
    ).fetchone()

    if not row:
        return _CACHE_MISS

    return json.loads(row[0])


def cache_set(namespace: str, cache_key: str, payload) -> None:
    serialized_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    connection = _connect()
    with connection:
        connection.execute(
            """
            INSERT INTO metadata_cache(namespace, cache_key, payload, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(namespace, cache_key)
            DO UPDATE SET payload = excluded.payload, updated_at = CURRENT_TIMESTAMP
            """,
            (namespace, cache_key, serialized_payload),
        )


def cache_clear_namespaces(*namespaces: str) -> int:
    cleaned_namespaces = tuple(namespace for namespace in namespaces if namespace)
    if not cleaned_namespaces:
        return 0

    connection = _connect()
    placeholders = ",".join("?" for _ in cleaned_namespaces)
    with connection:
        cursor = connection.execute(
            f"DELETE FROM metadata_cache WHERE namespace IN ({placeholders})",
            cleaned_namespaces,
        )
    return int(cursor.rowcount or 0)
