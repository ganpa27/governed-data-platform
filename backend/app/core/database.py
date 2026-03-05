"""
app/core/database.py
────────────────────
Databricks SQL connection management.

Design decisions:
  - Uses a connection-per-request pattern (connector is NOT thread-safe to share).
  - get_connection() is a context manager that always closes the connection.
  - execute_query() is the single point of execution used across all services.

macOS SSL Fix:
  Python on macOS does NOT use the system certificate store correctly.
  ssl.create_default_context() fails to verify Databricks cloud certificates.
  Fix: pass _tls_trusted_ca_file=certifi.where() to the connector.
  This uses the certifi CA bundle (trusted, up-to-date, cross-platform).
  TLS validation remains fully enabled — this is production-safe.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

import certifi
from databricks import sql as dbsql

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@contextmanager
def get_connection():
    """
    Yield a fresh Databricks SQL connection for the duration of the block.
    The connection is always closed, even on error.

    Uses certifi CA bundle for cross-platform TLS validation (fixes macOS).

    Usage:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
    """
    conn = None
    try:
        print("Opening Databricks connection...")  # debug print
        conn = dbsql.connect(
            server_hostname      = settings.databricks_server_hostname,
            http_path            = settings.databricks_http_path,
            access_token         = settings.databricks_token,
            _tls_trusted_ca_file = certifi.where(),   # ← macOS SSL fix (production-safe)
        )
        logger.debug("Databricks connection opened.")
        yield conn
    except Exception as exc:
        logger.exception("Failed to open Databricks connection.")
        raise
    finally:
        if conn:
            conn.close()
            logger.debug("Databricks connection closed.")


def execute_query(sql: str) -> list[dict[str, Any]]:
    """
    Execute a SQL statement and return results as a list of dicts.

    This is the ONLY place in the codebase where SQL is sent to Databricks.
    All callers (predefined reports, free-SQL engine, AI layer) route here.

    Args:
        sql: A fully formed, validated SQL string.

    Returns:
        List of row dicts keyed by column name.

    Raises:
        Exception on any Databricks error — callers handle HTTP semantics.
    """
    logger.info("Executing SQL: %s", sql[:200])  # truncate for log safety
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

    result = [dict(zip(columns, row)) for row in rows]
    logger.info("Query returned %d rows.", len(result))
    return result
