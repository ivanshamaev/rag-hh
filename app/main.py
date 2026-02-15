"""
API: индексация вакансий, векторный поиск, RAG (контекст для ответа).
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.vacancies import (
    DEFAULT_DATA_ENGINEER_QUERIES,
    get_stats,
    load_and_index_vacancies,
    load_and_index_vacancies_multi,
    process_raw_to_rag,
    search_similar,
)

app = FastAPI(
    title="RAG HH",
    description="Векторный поиск по вакансиям hh.ru с pgvector. RAG: семантический поиск + контекст.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    search_query: str = "python"
    max_vacancies: int = 30


class IngestBulkRequest(BaseModel):
    """Этап 1: выгрузка до target_count вакансий в raw_vacancies (дедупликация по hh_id)."""

    search_queries: list[str] | None = None
    target_count: int = 1000
    chunk_size: int = 10
    detail_delay_sec: float = 2.0


class EmbedFromRawRequest(BaseModel):
    """Этап 2: построить эмбеддинги из raw_vacancies и записать в rag_vacancies."""

    limit: int | None = None  # макс. строк из raw (None = все)
    chunk_size: int = 50  # пачка для embed_batch


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def stats():
    """Статистика по индексированным вакансиям: количество, компании, регионы, зарплаты."""
    try:
        return get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest")
def ingest(body: IngestRequest | None = None):
    """
    Этап 1: выгрузить вакансии с hh.ru в public.raw_vacancies (только id + json).
    Эмбеддинги — отдельно: POST /ingest/embed.
    """
    body = body or IngestRequest()
    try:
        n = load_and_index_vacancies(
            search_query=body.search_query,
            max_vacancies=min(body.max_vacancies, 100),
        )
        return {"saved_to_raw": n, "search_query": body.search_query}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/bulk")
def ingest_bulk(body: IngestBulkRequest | None = None):
    """
    Этап 1: выгрузить до target_count вакансий по запросам в public.raw_vacancies.
    Эмбеддинги — отдельно: POST /ingest/embed.
    """
    body = body or IngestBulkRequest()
    try:
        n = load_and_index_vacancies_multi(
            search_queries=body.search_queries,
            target_count=min(body.target_count, 2000),
            chunk_size=min(max(body.chunk_size, 5), 100),
            detail_delay_sec=max(1.0, min(body.detail_delay_sec, 30.0)),
        )
        queries = body.search_queries or DEFAULT_DATA_ENGINEER_QUERIES
        return {"saved_to_raw": n, "search_queries": queries, "target_count": body.target_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/embed")
def ingest_embed(body: EmbedFromRawRequest | None = None):
    """
    Этап 2: прочитать public.raw_vacancies, построить эмбеддинги и записать в public.rag_vacancies.
    Вызывать после POST /ingest или POST /ingest/bulk.
    """
    body = body or EmbedFromRawRequest()
    try:
        n = process_raw_to_rag(limit=body.limit, chunk_size=min(max(body.chunk_size, 10), 200))
        return {"rag_indexed": n, "limit": body.limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search")
def search(
    q: str = Query(..., description="Поисковый запрос (семантический)"),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Векторный поиск: запрос переводится в эмбеддинг, ищутся ближайшие вакансии (cosine).
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query is empty")
    try:
        results = search_similar(query=q, limit=limit)
        return {"query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/rag")
def rag(
    q: str = Query(..., description="Вопрос для RAG"),
    limit: int = Query(5, ge=1, le=20),
):
    """
    RAG: семантический поиск по вакансиям + возврат контекста (топ-N вакансий).
    Контекст можно передать в LLM для генерации ответа.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query is empty")
    try:
        results = search_similar(query=q, limit=limit)
        context_parts = []
        for i, r in enumerate(results, 1):
            ctx = f"[Вакансия {i}] {r['name']}"
            if r.get("employer_name"):
                ctx += f" — {r['employer_name']}"
            if r.get("area_name"):
                ctx += f" ({r['area_name']})"
            if r.get("description"):
                ctx += f"\n{r['description']}"
            context_parts.append(ctx)
        context = "\n\n---\n\n".join(context_parts)
        return {
            "query": q,
            "context": context,
            "sources": [{"name": r["name"], "url": r["url"], "similarity": r["similarity"]} for r in results],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
