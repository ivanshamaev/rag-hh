# RAG HH — векторный поиск по вакансиям hh.ru (pgvector)

Pet project: **векторный поиск в PostgreSQL с pgvector** и **RAG** по вакансиям с [hh.ru](https://hh.ru).

## Что внутри

- **PostgreSQL 16 + pgvector** — хранение вакансий и векторов эмбеддингов (384 размерности).
- **Эмбеддинги** — модель `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers), локально, поддерживает русский.
- **Загрузка вакансий** — публичный API hh.ru (поиск + детали по id).
- **Поиск** — косинусная близость `embedding <=> query_vector` в pgvector.
- **RAG** — семантический поиск по вакансиям и возврат контекста (топ-N вакансий) для последующей передачи в LLM.

## Запуск в Docker

```bash
cd rag-hh
docker compose up --build
```

- БД: `localhost:5432`, пользователь `rag`, пароль `rag`, БД `rag_hh`.
- API: http://localhost:8001  
- Документация: http://localhost:8001/docs  

Первый запуск приложения займёт время: скачивание образа PostgreSQL, установка зависимостей и загрузка модели эмбеддингов при первом запросе.

## Шаги работы

### 1. Индексация вакансий

Отправить запрос на загрузку вакансий с hh.ru и построение эмбеддингов:

```bash
curl -X POST http://localhost:8001/ingest \
  -H "Content-Type: application/json" \
  -d '{"search_query": "python backend", "max_vacancies": 30}'
```

Или в Swagger: **POST /ingest** с телом `{"search_query": "python", "max_vacancies": 30}`.

Данные сохраняются в таблицу `vacancies` (поля + вектор в колонке `embedding`).

### 2. Векторный поиск

Поиск по смыслу (не по ключевым словам):

```bash
curl "http://localhost:8001/search?q=удалённая%20работа%20python&limit=5"
```

Ответ: список вакансий с полем `similarity` (косинусная близость).

### 3. RAG — контекст для ответа

Получить контекст по вопросу (топ релевантных вакансий) для передачи в LLM:

```bash
curl "http://localhost:8001/rag?q=Какие%20вакансии%20по%20Python%20с%20удалёнкой?&limit=5"
```

В ответе: `query`, `context` (склеенный текст вакансий), `sources` (ссылки и similarity).

## Схема БД (pgvector)

```sql
CREATE EXTENSION vector;

CREATE TABLE vacancies (
    id BIGSERIAL PRIMARY KEY,
    hh_id VARCHAR(32) UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    employer_name TEXT,
    area_name TEXT,
    salary_from INTEGER,
    salary_to INTEGER,
    url TEXT,
    published_at TIMESTAMPTZ,
    embedding vector(384)   -- MiniLM-L12
);

-- Индекс для приближённого поиска (IVFFlat)
CREATE INDEX vacancies_embedding_idx ON vacancies
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

- **Точный поиск** — `ORDER BY embedding <=> $1 LIMIT k` (без индекса подходит для небольших объёмов).
- **Приближённый (IVFFlat)** — быстрее на больших таблицах; точность настраивается параметром `lists`.

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | Подключение к PostgreSQL (по умолчанию `postgresql://rag:rag@db:5432/rag_hh`) |
| `EMBEDDING_MODEL` | Модель sentence-transformers (по умолчанию `paraphrase-multilingual-MiniLM-L12-v2`) |

Для локального запуска без Docker задайте `DATABASE_URL` с хостом `localhost`.

## Зависимости

- Python 3.11+, psycopg3, pgvector, sentence-transformers, FastAPI, httpx.
- Для локального запуска (без Docker): `pip install torch` или CPU-версия:  
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`

## Лицензия

MIT.
