"""
Сохранение вакансий и эмбеддингов в PostgreSQL (pgvector).
"""
from datetime import datetime
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from app.db import get_connection_sync, list_to_pgvector
from app.embeddings import embed_batch
from app.hh_client import fetch_vacancy_detail, fetch_vacancies, vacancy_to_text


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


def load_and_index_vacancies(search_query: str = "python", max_vacancies: int = 50) -> int:
    """
    Загрузить вакансии с hh.ru, посчитать эмбеддинги и сохранить в БД.
    Возвращает количество проиндексированных вакансий.
    """
    items = fetch_vacancies(text=search_query, per_page=20, max_pages=3)
    if not items:
        return 0

    # Ограничиваем и подгружаем полные описания
    to_process = items[:max_vacancies]
    vacancies_data: list[dict[str, Any]] = []
    for it in to_process:
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
                description=v.get("description"),
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
