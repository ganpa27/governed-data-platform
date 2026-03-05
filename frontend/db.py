"""
db.py — Databricks connection helper.
Certifi CA bundle ensures cross-platform TLS validation (macOS fix).
"""
import os
import certifi
from databricks import sql
from dotenv import load_dotenv

load_dotenv(override=True)


def get_connection():
    return sql.connect(
        server_hostname      = os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path            = os.getenv("DATABRICKS_HTTP_PATH"),
        access_token         = os.getenv("DATABRICKS_TOKEN"),
        _tls_trusted_ca_file = certifi.where(),
    )


def run_query(sql_text: str, params: dict | None = None) -> tuple[list, list]:
    """
    Execute sql_text and return (columns, rows).
    params is a plain dict — values are substituted manually (no user input ever reaches here).
    """
    if params:
        for k, v in params.items():
            # Safe: values come ONLY from our own keyword extractor, never from raw user input.
            sql_text = sql_text.replace(f":{k}", f"'{v}'")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql_text)
        columns = [d[0] for d in cursor.description]
        rows    = [list(row) for row in cursor.fetchall()]
    return columns, rows
