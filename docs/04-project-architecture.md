# Архитектура проекта RAG HH

Как устроено приложение: компоненты, поток данных и API. После прочтения вы сможете уверенно ориентироваться в коде и расширять проект.

---

## 1. Обзор стека

| Слой | Технология | Роль |
|------|------------|------|
| БД | PostgreSQL 16 + pgvector | Хранение вакансий и векторов, векторный поиск |
| Backend | Python 3.11, FastAPI | API, оркестрация индексации и поиска |
| Эмбеддинги | sentence-transformers | Локальная модель, русский + английский |
| Данные | hh.ru API | Загрузка вакансий по поисковому запросу |
| Инфра | Docker Compose | БД и приложение в контейнерах |

---

## 2. Структура репозитория

```
rag-hh/
├── app/
│   ├── __init__.py
│   ├── config.py      # Настройки (DATABASE_URL, EMBEDDING_MODEL)
│   ├── db.py          # Подключение к PostgreSQL, register_vector, list_to_pgvector
│   ├── embeddings.py  # Загрузка модели, embed() / embed_batch()
│   ├── hh_client.py   # Запросы к api.hh.ru, vacancy_to_text()
│   ├── main.py        # FastAPI: /health, /ingest, /search, /rag
│   └── vacancies.py   # upsert, load_and_index_vacancies(), search_similar()
├── db/
│   └── init.sql       # CREATE EXTENSION vector, таблица vacancies, индекс IVFFlat
├── docs/              # Документация (этот гайд и остальные)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 3. Поток данных

### 3.1 Индексация (POST /ingest)

```
Пользователь → POST /ingest { search_query, max_vacancies }
       │
       ▼
main.ingest() → vacancies.load_and_index_vacancies()
       │
       ├─► hh_client.fetch_vacancies(search_query)     → список кратких вакансий (id, name, …)
       │
       ├─► для каждой: hh_client.fetch_vacancy_detail(id) → полная вакансия
       │
       ├─► hh_client.vacancy_to_text(v) для каждой     → текст для эмбеддинга
       │
       ├─► embeddings.embed_batch(texts)                → список векторов
       │
       └─► db: vacancies.upsert_vacancy(…, embedding)  → INSERT/UPDATE в PostgreSQL
```

Итог: в таблице `vacancies` появляются или обновляются строки с полями вакансии и колонкой `embedding`.

### 3.2 Поиск (GET /search)

```
Пользователь → GET /search?q=...&limit=...
       │
       ▼
main.search() → vacancies.search_similar(query, limit)
       │
       ├─► embeddings.embed(query)                    → вектор запроса
       │
       └─► PostgreSQL: ORDER BY embedding <=> $1 LIMIT $2
              → список вакансий + similarity (1 - cosine_distance)
       │
       ▼
Ответ JSON: { query, results: [{ name, description, url, similarity, … }] }
```

### 3.3 RAG-контекст (GET /rag)

```
Пользователь → GET /rag?q=...&limit=...
       │
       ▼
main.rag() → тот же search_similar(query, limit)
       │
       ▼
Формирование context: для каждой вакансии — блок "[Вакансия N] название — работодатель (город)\nописание"
       │
       ▼
Ответ JSON: { query, context (склеенный текст), sources (name, url, similarity) }
```

Контекст готов для подстановки в промпт LLM; вызов самой LLM в коде не реализован.

---

## 4. Компоненты по файлам

### app/config.py

- Читает `DATABASE_URL` и `EMBEDDING_MODEL` из окружения (и опционально `.env`).
- Используется в `db.py` и `embeddings.py`.

### app/db.py

- `get_connection()` / `get_connection_sync()` — подключение к PostgreSQL, после подключения вызывается `register_vector(conn)` для работы типа `vector` в psycopg.
- `list_to_pgvector(vec)` — превращает `list[float]` в строку `'[0.1, 0.2, ...]'` для передачи в SQL как `%s::vector`.

### app/embeddings.py

- `get_embedding_model()` — ленивая загрузка модели (с кэшем), модель из `settings.embedding_model`.
- `embed(text)` — один текст → вектор (list[float]).
- `embed_batch(texts, batch_size=32)` — пакет текстов → список векторов; используется при индексации.

### app/hh_client.py

- `fetch_vacancies(text, per_page, max_pages)` — поиск вакансий через GET /vacancies, пагинация, пауза между запросами.
- `fetch_vacancy_detail(vacancy_id)` — GET /vacancies/{id} для полного описания.
- `vacancy_to_text(v)` — из объекта вакансии собирает один текст (название + описание без HTML + навыки), обрезка описания до 3000 символов.

### app/vacancies.py

- `upsert_vacancy(conn, …)` — один INSERT ... ON CONFLICT (hh_id) DO UPDATE с полями вакансии и вектором.
- `load_and_index_vacancies(search_query, max_vacancies)` — полный цикл: загрузка с hh.ru → тексты → эмбеддинги → upsert в БД; возвращает число проиндексированных.
- `search_similar(query, limit)` — эмбеддинг запроса, SQL с `ORDER BY embedding <=> $1 LIMIT $2`, возврат списка словарей с полями вакансии и `similarity`.

### app/main.py

- FastAPI-приложение, три эндпоинта: `/health`, `POST /ingest`, `GET /search`, `GET /rag`.
- Валидация запросов (Query, body), вызов функций из `vacancies`, обработка ошибок.

### db/init.sql

- Выполняется при первом запуске контейнера PostgreSQL (docker-entrypoint-initdb.d).
- Создаёт расширение `vector`, таблицу `vacancies` с колонкой `embedding vector(384)`, индекс IVFFlat по косинусному расстоянию.

---

## 5. Зависимости между модулями

```
main.py
  └── vacancies (load_and_index_vacancies, search_similar)

vacancies.py
  ├── db (get_connection_sync, list_to_pgvector)
  ├── embeddings (embed, embed_batch)
  └── hh_client (fetch_vacancies, fetch_vacancy_detail, vacancy_to_text)

embeddings.py
  └── config (settings)

hh_client.py
  └── (нет внутренних зависимостей проекта)

db.py
  └── config (settings)
```

---

## 6. Расширение проекта: идеи

- **Добавить вызов LLM** после получения контекста в `/rag`: взять `query` и `context`, собрать промпт, вызвать API (OpenAI, Ollama и т.д.), вернуть ответ + sources.
- **Гибридный поиск**: полнотекстовый поиск PostgreSQL по `name`/`description` и объединение с векторным (например, по скору).
- **Chunking**: если появятся очень длинные документы — разбивать на чанки, хранить чанки с `document_id`, искать по чанкам, в контекст подставлять чанки или родительские документы.
- **Другая модель эмбеддингов**: поменять `EMBEDDING_MODEL`, убедиться, что размерность совпадает с `vector(N)` в БД; при смене размерности — миграция колонки и переиндексация.

Дальше: [hh.ru API и индексация](05-hh-api-and-ingest.md) — детали загрузки и подготовки данных.
