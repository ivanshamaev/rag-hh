"""
API: индексация вакансий, векторный поиск, RAG (контекст для ответа).
"""
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.vacancies import load_and_index_vacancies, search_similar

app = FastAPI(
    title="RAG HH",
    description="Векторный поиск по вакансиям hh.ru с pgvector. RAG: семантический поиск + контекст.",
)


class IngestRequest(BaseModel):
    search_query: str = "python"
    max_vacancies: int = 30


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest(body: IngestRequest | None = None):
    """
    Загрузить вакансии с hh.ru по запросу, построить эмбеддинги и сохранить в pgvector.
    Первый запуск может занять время (скачивание модели + запросы к API).
    """
    body = body or IngestRequest()
    try:
        n = load_and_index_vacancies(
            search_query=body.search_query,
            max_vacancies=min(body.max_vacancies, 100),
        )
        return {"indexed": n, "search_query": body.search_query}
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
