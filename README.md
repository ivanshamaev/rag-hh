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
- **Frontend (Vue.js)** — в контейнере: http://localhost:3000 (дашборд, поиск, RAG). Запросы к API идут через nginx (`/api` → backend). Локальная разработка: `cd frontend && npm run dev` → http://localhost:5173.

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

### 1. Индексация вакансий (два этапа)

**Этап 1 — выгрузка в сыром виде:** вакансии с hh.ru сохраняются в `public.raw_vacancies` (только `hh_id` + полный JSON ответа API).

```bash
curl -X POST http://localhost:8001/ingest \
  -H "Content-Type: application/json" \
  -d '{"search_query": "python backend", "max_vacancies": 30}'
```

Массовая выгрузка (Data Engineer и др.):

```bash
curl -X POST http://localhost:8001/ingest/bulk \
  -H "Content-Type: application/json" \
  -d '{"target_count": 1000, "chunk_size": 10}'
```

Или скрипт: `python scripts/ingest_bulk.py --target 1000`. Выгрузка займёт время из-за лимитов hh.ru.

**Этап 2 — эмбеддинги и RAG:** из `raw_vacancies` строятся тексты, эмбеддинги и запись в `public.rag_vacancies` (поиск и дашборд работают с этой таблицей).

```bash
curl -X POST http://localhost:8001/ingest/embed \
  -H "Content-Type: application/json" \
  -d '{}'
```

Тело опционально: `{"limit": 500, "chunk_size": 50}` — обработать не более 500 сырых записей пачками по 50.

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

Два этапа хранения:

- **`public.raw_vacancies`** — этап выгрузки: `hh_id` (PK), `raw_json` (JSONB), `created_at`. Только сырой ответ API.
- **`public.rag_vacancies`** — этап RAG: `hh_id`, название, описание (без HTML), работодатель, регион, зарплата, url, `published_at`, `embedding` (vector 384). Поиск и дашборд читают отсюда.

Индекс для поиска: `rag_vacancies_embedding_idx` (IVFFlat). Для уже существующих БД без этих таблиц: `psql ... -f db/migrations/03_raw_and_rag_vacancies.sql`.

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
