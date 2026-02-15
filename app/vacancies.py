"""
Сохранение вакансий и эмбеддингов в PostgreSQL (pgvector).
"""
import json
import time
from datetime import datetime
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from app.db import get_connection_sync, list_to_pgvector
from app.embeddings import embed_batch
from app.hh_client import (
    PER_PAGE_MAX,
    fetch_vacancy_detail,
    fetch_vacancies,
    strip_html,
    vacancy_to_text,
)


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def upsert_raw_vacancy(conn: psycopg.Connection, hh_id: str, raw_json: dict[str, Any]) -> None:
    """Сохранить сырой ответ API hh.ru в public.raw_vacancies (этап 1 — только выгрузка)."""
    raw_str = json.dumps(raw_json, ensure_ascii=False, default=str)
    conn.execute(
        """
        INSERT INTO public.raw_vacancies (hh_id, raw_json)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (hh_id) DO UPDATE SET raw_json = EXCLUDED.raw_json
        """,
        (hh_id, raw_str),
    )


def upsert_rag_vacancy(
    conn: psycopg.Connection,
    hh_id: str,
    name: str,
    description: str | None,
    employer_name: str | None,
    area_name: str | None,
    salary_from: int | None,
    salary_to: int | None,
    url: str | None,
    published_at: datetime | None,
    embedding: list[float],
) -> None:
    """Записать вакансию с эмбеддингом в public.rag_vacancies (этап 2 — после преобразований)."""
    conn.execute(
        """
        INSERT INTO public.rag_vacancies (
            hh_id, name, description, employer_name, area_name,
            salary_from, salary_to, url, published_at, embedding
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
        ON CONFLICT (hh_id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            employer_name = EXCLUDED.employer_name,
            area_name = EXCLUDED.area_name,
            salary_from = EXCLUDED.salary_from,
            salary_to = EXCLUDED.salary_to,
            url = EXCLUDED.url,
            published_at = EXCLUDED.published_at,
            embedding = EXCLUDED.embedding
        """,
        (
            hh_id,
            name,
            description,
            employer_name,
            area_name,
            salary_from,
            salary_to,
            url,
            published_at,
            list_to_pgvector(embedding),
        ),
    )


def load_and_index_vacancies(
    search_query: str = "python",
    max_vacancies: int = 50,
    detail_delay_sec: float = 1.2,
) -> int:
    """
    Этап 1: выгрузить вакансии с hh.ru в public.raw_vacancies (только id + json).
    Эмбеддинги и rag_vacancies — отдельно, через process_raw_to_rag() или POST /ingest/embed.
    """
    items = fetch_vacancies(text=search_query, per_page=PER_PAGE_MAX, max_pages=5)
    if not items:
        return 0

    to_process = items[:max_vacancies]
    conn = get_connection_sync()
    try:
        saved = 0
        for i, it in enumerate(to_process):
            if i > 0:
                time.sleep(detail_delay_sec)
            try:
                full = fetch_vacancy_detail(it["id"])
                if full:
                    upsert_raw_vacancy(conn, str(full["id"]), full)
                    saved += 1
            except Exception:
                continue
        conn.commit()
        return saved
    finally:
        conn.close()


# Ключевые слова для поиска вакансий Data Engineer (рус + англ)
DEFAULT_DATA_ENGINEER_QUERIES = [
    "data engineer",
    "дата инженер",
    "инженер данных",
    "dwh инженер",
    "etl инженер",
    "data engineer python",
    "инженер данных etl",
    "big data инженер",
    "data engineer sql",
]


def _chunks(lst: list[Any], size: int):
    """Разбить список на чанки заданного размера."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def load_and_index_vacancies_multi(
    search_queries: list[str] | None = None,
    target_count: int = 1000,
    per_page: int = PER_PAGE_MAX,
    max_pages_per_query: int = 5,
    search_field: str = "name",
    detail_delay_sec: float = 2.0,
    chunk_size: int = 10,
) -> int:
    """
    Этап 1: выгрузка по нескольким запросам в public.raw_vacancies (только id + json).
    Чанками: запрос N деталей → запись в raw. Эмбеддинги — отдельно (process_raw_to_rag).
    """
    queries = search_queries or DEFAULT_DATA_ENGINEER_QUERIES
    seen_ids: set[str] = set()
    unique_ids: list[str] = []

    for text in queries:
        items = fetch_vacancies(
            text=text,
            per_page=per_page,
            max_pages=max_pages_per_query,
            search_field=search_field,
        )
        for it in items:
            vid = str(it.get("id", ""))
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                unique_ids.append(vid)
                if len(unique_ids) >= target_count:
                    break
        if len(unique_ids) >= target_count:
            break

    id_list = unique_ids[:target_count]
    if not id_list:
        return 0

    total_saved = 0
    conn = get_connection_sync()
    try:
        for id_chunk in _chunks(id_list, chunk_size):
            for i, vid in enumerate(id_chunk):
                if i > 0:
                    time.sleep(detail_delay_sec)
                try:
                    full = fetch_vacancy_detail(vid)
                    if full:
                        upsert_raw_vacancy(conn, str(full["id"]), full)
                        total_saved += 1
                except Exception:
                    continue
            conn.commit()
        return total_saved
    finally:
        conn.close()


def load_and_index_vacancy_ids(
    id_list: list[str],
    chunk_size: int = 10,
    detail_delay_sec: float = 2.0,
) -> int:
    """
    Этап 1: по списку hh_id загрузить детали с API и сохранить в public.raw_vacancies.
    Эмбеддинги — отдельно (process_raw_to_rag).
    """
    if not id_list:
        return 0
    total_saved = 0
    conn = get_connection_sync()
    try:
        for id_chunk in _chunks(id_list, chunk_size):
            for i, vid in enumerate(id_chunk):
                if i > 0:
                    time.sleep(detail_delay_sec)
                try:
                    full = fetch_vacancy_detail(vid)
                    if full:
                        upsert_raw_vacancy(conn, str(full["id"]), full)
                        total_saved += 1
                except Exception:
                    continue
            conn.commit()
        return total_saved
    finally:
        conn.close()


def process_raw_to_rag(
    limit: int | None = None,
    chunk_size: int = 50,
) -> int:
    """
    Этап 2: прочитать из public.raw_vacancies, преобразовать (strip_html, текст для эмбеддинга),
    посчитать эмбеддинги и записать в public.rag_vacancies.
    limit: максимум строк из raw (None = все). chunk_size: пачка для embed_batch.
    """
    conn = get_connection_sync()
    register_vector(conn)
    try:
        if limit is not None:
            cur = conn.execute(
                "SELECT hh_id, raw_json FROM public.raw_vacancies ORDER BY created_at LIMIT %s",
                (limit,),
            )
        else:
            cur = conn.execute("SELECT hh_id, raw_json FROM public.raw_vacancies ORDER BY created_at")
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return 0

    total = 0
    conn = get_connection_sync()
    register_vector(conn)
    try:
        for chunk in _chunks(rows, chunk_size):
            vacancies_data: list[dict[str, Any]] = []
            for _hh_id, raw_json in chunk:
                v = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                if isinstance(v, dict):
                    vacancies_data.append(v)

            if not vacancies_data:
                continue

            texts = [vacancy_to_text(v) for v in vacancies_data]
            embeddings = embed_batch(texts)
            for v, emb in zip(vacancies_data, embeddings):
                salary = v.get("salary")
                area = v.get("area", {}) or {}
                employer = v.get("employer", {}) or {}
                upsert_rag_vacancy(
                    conn=conn,
                    hh_id=str(v["id"]),
                    name=v.get("name", ""),
                    description=strip_html(v.get("description")),
                    employer_name=employer.get("name"),
                    area_name=area.get("name"),
                    salary_from=salary.get("salary_from") if salary else None,
                    salary_to=salary.get("salary_to") if salary else None,
                    url=v.get("alternate_url"),
                    published_at=parse_date(v.get("published_at")),
                    embedding=emb,
                )
            conn.commit()
            total += len(vacancies_data)
        return total
    finally:
        conn.close()


def get_stats() -> dict[str, Any]:
    """Агрегатная статистика по вакансиям для дашборда (из public.rag_vacancies)."""
    conn = get_connection_sync()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM public.rag_vacancies")
        total_vacancies = cur.fetchone()[0] or 0

        cur = conn.execute(
            "SELECT COUNT(DISTINCT employer_name) FROM public.rag_vacancies WHERE employer_name IS NOT NULL AND employer_name != ''"
        )
        unique_employers = cur.fetchone()[0] or 0

        cur = conn.execute(
            """
            SELECT area_name, COUNT(*) AS cnt FROM public.rag_vacancies
            WHERE area_name IS NOT NULL AND area_name != ''
            GROUP BY area_name ORDER BY cnt DESC LIMIT 10
            """
        )
        top_areas = [{"name": r[0], "count": r[1]} for r in cur.fetchall()]

        cur = conn.execute(
            "SELECT COUNT(*) FROM public.rag_vacancies WHERE salary_from IS NOT NULL OR salary_to IS NOT NULL"
        )
        with_salary = cur.fetchone()[0] or 0

        cur = conn.execute(
            "SELECT AVG(salary_from), AVG(salary_to) FROM public.rag_vacancies WHERE salary_from IS NOT NULL"
        )
        row = cur.fetchone()
        avg_salary_from = round(row[0], 0) if row and row[0] is not None else None
        avg_salary_to = round(row[1], 0) if row and row[1] is not None else None

        cur = conn.execute("SELECT COUNT(*) FROM public.raw_vacancies")
        raw_count = cur.fetchone()[0] or 0

        return {
            "total_vacancies": total_vacancies,
            "unique_employers": unique_employers,
            "top_areas": top_areas,
            "vacancies_with_salary": with_salary,
            "avg_salary_from": avg_salary_from,
            "avg_salary_to": avg_salary_to,
            "raw_vacancies_count": raw_count,
        }
    finally:
        conn.close()


def search_similar(
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Векторный поиск: эмбеддинг запроса и поиск ближайших вакансий (cosine).
    """
    from app.embeddings import embed

    query_vec = embed(query)
    conn = get_connection_sync()
    register_vector(conn)
    try:
        cur = conn.execute(
            """
            SELECT hh_id, name, description, employer_name, area_name,
                   salary_from, salary_to, url,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM public.rag_vacancies
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (list_to_pgvector(query_vec), list_to_pgvector(query_vec), limit),
        )
        rows = cur.fetchall()
        return [
            {
                "hh_id": r[0],
                "name": r[1],
                "description": (r[2] or "")[:500],
                "employer_name": r[3],
                "area_name": r[4],
                "salary_from": r[5],
                "salary_to": r[6],
                "url": r[7],
                "similarity": round(float(r[8]), 4),
            }
            for r in rows
        ]
    finally:
        conn.close()
