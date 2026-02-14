"""
Сохранение вакансий и эмбеддингов в PostgreSQL (pgvector).
"""
import time
from datetime import datetime
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from app.db import get_connection_sync, list_to_pgvector
from app.embeddings import embed_batch
from app.hh_client import fetch_vacancy_detail, fetch_vacancies, strip_html, vacancy_to_text


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def upsert_vacancy(
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
    conn.execute(
        """
        INSERT INTO vacancies (
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
    Загрузить вакансии с hh.ru, посчитать эмбеддинги и сохранить в БД.
    Возвращает количество проиндексированных вакансий.
    """
    items = fetch_vacancies(text=search_query, per_page=20, max_pages=3)
    if not items:
        return 0

    # Ограничиваем и подгружаем полные описания (с паузой между запросами к API)
    to_process = items[:max_vacancies]
    vacancies_data: list[dict[str, Any]] = []
    for i, it in enumerate(to_process):
        if i > 0:
            time.sleep(detail_delay_sec)
        full = fetch_vacancy_detail(it["id"])
        if full:
            vacancies_data.append(full)

    if not vacancies_data:
        return 0

    texts = [vacancy_to_text(v) for v in vacancies_data]
    embeddings = embed_batch(texts)

    conn = get_connection_sync()
    register_vector(conn)
    try:
        for v, emb in zip(vacancies_data, embeddings):
            salary = v.get("salary")
            area = v.get("area", {}) or {}
            employer = v.get("employer", {}) or {}
            upsert_vacancy(
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
        return len(vacancies_data)
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


def load_and_index_vacancies_multi(
    search_queries: list[str] | None = None,
    target_count: int = 1000,
    per_page: int = 100,
    max_pages_per_query: int = 5,
    search_field: str = "name",
    detail_delay_sec: float = 1.2,
) -> int:
    """
    Загрузка вакансий по нескольким поисковым запросам с дедупликацией по hh_id.
    Подходит для набора ~1000 вакансий по смежным формулировкам (например, Data Engineer).
    search_field: по API hh.ru допустимы только name, company_name, description (не "all").
    """
    queries = search_queries or DEFAULT_DATA_ENGINEER_QUERIES
    seen_ids: set[str] = set()
    unique_items: list[dict[str, Any]] = []

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
                unique_items.append(it)
                if len(unique_items) >= target_count:
                    break
        if len(unique_items) >= target_count:
            break

    to_process = unique_items[:target_count]
    if not to_process:
        return 0

    vacancies_data: list[dict[str, Any]] = []
    for i, it in enumerate(to_process):
        if i > 0:
            time.sleep(detail_delay_sec)
        full = fetch_vacancy_detail(it["id"])
        if full:
            vacancies_data.append(full)

    if not vacancies_data:
        return 0

    texts = [vacancy_to_text(v) for v in vacancies_data]
    embeddings = embed_batch(texts)

    conn = get_connection_sync()
    register_vector(conn)
    try:
        for v, emb in zip(vacancies_data, embeddings):
            salary = v.get("salary")
            area = v.get("area", {}) or {}
            employer = v.get("employer", {}) or {}
            upsert_vacancy(
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
        return len(vacancies_data)
    finally:
        conn.close()


def get_stats() -> dict[str, Any]:
    """Агрегатная статистика по вакансиям для дашборда."""
    conn = get_connection_sync()
    try:
        # Всего вакансий
        cur = conn.execute("SELECT COUNT(*) FROM vacancies")
        total_vacancies = cur.fetchone()[0] or 0

        # Уникальных работодателей
        cur = conn.execute(
            "SELECT COUNT(DISTINCT employer_name) FROM vacancies WHERE employer_name IS NOT NULL AND employer_name != ''"
        )
        unique_employers = cur.fetchone()[0] or 0

        # Топ регионов по количеству вакансий
        cur = conn.execute(
            """
            SELECT area_name, COUNT(*) AS cnt FROM vacancies
            WHERE area_name IS NOT NULL AND area_name != ''
            GROUP BY area_name ORDER BY cnt DESC LIMIT 10
            """
        )
        top_areas = [{"name": r[0], "count": r[1]} for r in cur.fetchall()]

        # Вакансии с указанной зарплатой
        cur = conn.execute(
            "SELECT COUNT(*) FROM vacancies WHERE salary_from IS NOT NULL OR salary_to IS NOT NULL"
        )
        with_salary = cur.fetchone()[0] or 0

        # Средние вилки (только по тем, где указано)
        cur = conn.execute(
            "SELECT AVG(salary_from), AVG(salary_to) FROM vacancies WHERE salary_from IS NOT NULL"
        )
        row = cur.fetchone()
        avg_salary_from = round(row[0], 0) if row and row[0] is not None else None
        avg_salary_to = round(row[1], 0) if row and row[1] is not None else None

        return {
            "total_vacancies": total_vacancies,
            "unique_employers": unique_employers,
            "top_areas": top_areas,
            "vacancies_with_salary": with_salary,
            "avg_salary_from": avg_salary_from,
            "avg_salary_to": avg_salary_to,
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
            FROM vacancies
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
