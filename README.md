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
- **Frontend (Vue.js)** — в отдельном терминале: `cd frontend && npm i && npm run dev` → http://localhost:5173 (дашборд, семантический поиск, RAG). Прокси к API настроен в Vite.

**Если http://localhost:8001/docs недоступен:** 1) Запущен ли Docker: `docker compose up` (без `-d` — смотрите логи). 2) При запуске без Docker uvicorn слушает порт 8000 по умолчанию — откройте http://localhost:8000/docs или запустите `uvicorn app.main:app --reload --port 8001`. 3) Контейнер упал: `docker compose logs app` — проверьте ошибки (БД, импорты). 4) Проверка порта: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health` — должен вернуть 200.

Первый запуск приложения займёт время: скачивание образа PostgreSQL, установка зависимостей и загрузка модели эмбеддингов при первом запросе.

## Документация

Подробные руководства (эмбеддинги, pgvector, RAG, архитектура, hh.ru API, Docker) — в папке **[docs/](docs/README.md)**. Рекомендуется для углублённого понимания технологий и best practices.

### Frontend (Vue.js)

Полная документация по установке, запуску и сборке — **[frontend/README.md](frontend/README.md)**.

- **Локальный запуск:** `cd frontend && npm install && npm run dev` → http://localhost:5173 (нужен запущенный API на 8001).
- **Сборка:** `cd frontend && npm run build` → артефакты в `frontend/dist/`.
- **Просмотр сборки:** `npm run preview` → http://localhost:4173.

## Шаги работы

### 1. Индексация вакансий

Отправить запрос на загрузку вакансий с hh.ru и построение эмбеддингов:

```bash
curl -X POST http://localhost:8001/ingest \
  -H "Content-Type: application/json" \
  -d '{"search_query": "python backend", "max_vacancies": 30}'
```

Или в Swagger: **POST /ingest** с телом `{"search_query": "python", "max_vacancies": 30}`.

**Массовая загрузка ~1000 вакансий (Data Engineer и смежные):**

```bash
curl -X POST http://localhost:8001/ingest/bulk \
  -H "Content-Type: application/json" \
  -d '{"target_count": 1000}'
```

Или из терминала (без API): `python scripts/ingest_bulk.py --target 1000`. По умолчанию используются запросы: data engineer, дата инженер, инженер данных, dwh инженер, etl инженер и др.; результаты объединяются с дедупликацией по id. Загрузка займёт 20–40 минут из-за лимитов hh.ru.

Данные сохраняются в таблицу `vacancies` (поля + вектор в колонке `embedding`).

### 2. Векторный поиск и RAG в браузере

Запустите фронтенд: `cd frontend && npm i && npm run dev`, откройте http://localhost:5173 (API должен быть доступен на http://localhost:8001 — например, через `docker compose up`). В интерфейсе: **Дашборд** — статистика (вакансии, компании, регионы, зарплаты); **Поиск** — семантический поиск по вакансиям; **RAG** — получение контекста (топ вакансий) с кнопкой «Копировать» для вставки в LLM.

Через API напрямую:

```bash
curl "http://localhost:8001/search?q=удалённая%20работа%20python&limit=5"
```

Ответ: список вакансий с полем `similarity` (косинусная близость).

### 3. RAG — контекст для ответа (API)

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
    embedding vector(384),  -- MiniLM-L12
    hh_response JSONB      -- полный ответ API hh.ru (GET /vacancies/{id})
);

-- Индекс для приближённого поиска (IVFFlat)
CREATE INDEX vacancies_embedding_idx ON vacancies
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

- **Точный поиск** — `ORDER BY embedding <=> $1 LIMIT k` (без индекса подходит для небольших объёмов).
- **Приближённый (IVFFlat)** — быстрее на больших таблицах; точность настраивается параметром `lists`.
- **hh_response** — в колонке хранится полный JSON-ответ API hh.ru по вакансии. Для уже существующих БД: `psql ... -f db/migrations/02_add_hh_response.sql`.

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | Подключение к PostgreSQL (по умолчанию `postgresql://rag:rag@db:5432/rag_hh`) |
| `EMBEDDING_MODEL` | Модель sentence-transformers (по умолчанию `paraphrase-multilingual-MiniLM-L12-v2`) |
| `HH_TOKEN` | Опционально: OAuth-токен hh.ru для повышенных лимитов (меньше ошибок SSL/429) |
| `HH_CLIENT_ID` | Опционально: client_id приложения hh.ru |
| `HH_CLIENT_SECRET` | Опционально: client_secret приложения hh.ru |

Для локального запуска без Docker задайте `DATABASE_URL` с хостом `localhost`.

**hh.ru OAuth:** все данные хранятся в `.env`: `HH_TOKEN`, `HH_CLIENT_ID`, `HH_CLIENT_SECRET`. Токен подставляется в заголовок `Authorization: Bearer` при запросах к api.hh.ru. Файл `.env` в `.gitignore` — секреты не коммитятся.

**Загрузка по ролям (Москва):** скрипт `scripts/ingest_by_roles.py` — вакансии по профессиональным ролям и региону (как в старом парсере). Пример: `python scripts/ingest_by_roles.py --area 1 --max-per-role 500 --roles "Дата-инженер"`.

## Зависимости

- Python 3.11+, psycopg3, pgvector, sentence-transformers, FastAPI, httpx.
- Для локального запуска (без Docker): `pip install torch` или CPU-версия:  
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`

## Лицензия

MIT.
