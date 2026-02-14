import json
from contextlib import contextmanager
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector

from app.config import settings


@contextmanager
def get_connection():
    conn = psycopg.connect(settings.database_url)
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connection_sync():
    conn = psycopg.connect(settings.database_url)
    register_vector(conn)
    return conn


def list_to_pgvector(vec: list[float]) -> str:
    """Формат для передачи в SQL: '[0.1, 0.2, ...]'"""
    return json.dumps(vec)
