# RAG Tutorial: полное руководство по проекту RAG HH

Практическое руководство по построению RAG-системы по вакансиям hh.ru: этапы разработки, архитектура, расчёт расстояний, получение топа из RAG, проектирование backend/frontend и работа с таблицей эмбеддингов. Материал собран из реализации проекта и переписки по разработке.

---

## 1. Обзор и этапы разработки

### 1.1 Что получилось в итоге

- **Загрузка вакансий** с hh.ru по поисковым запросам (в т.ч. массовая по нескольким запросам с дедупликацией по `hh_id`).
- **Два слоя хранения**: сырые ответы API (`raw_vacancies`) и слой для поиска/RAG (`rag_vacancies`) с эмбеддингами.
- **Векторный поиск** в PostgreSQL (pgvector) по косинусной близости.
- **RAG**: семантический поиск + формирование контекста (топ-N вакансий) для передачи в LLM.
- **Навыки**: извлечение из `key_skills` и глубокий анализ по тексту вакансии (поиск известных hard skills в названии и описании).
- **Frontend**: дашборд (статистика, регионы, навыки), семантический поиск, RAG с копированием контекста.
- **Инфраструктура**: Docker Compose (PostgreSQL + pgvector, приложение, frontend на nginx).

### 1.2 Этапы разработки (хронология)

| Этап | Что делали |
|------|------------|
| Загрузка вакансий | Массовая загрузка по нескольким запросам, дедупликация по `hh_id`, чанки, паузы между запросами к API. |
| Разделение raw / RAG | Выгрузка (POST /ingest, /ingest/bulk) пишет только в `raw_vacancies`. Эмбеддинги — отдельно: POST /ingest/embed вызывает `process_raw_to_rag()`. Поиск и дашборд работают с `rag_vacancies`. |
| HTML в описаниях | В hh_client добавлена `strip_html()`; используется при формировании текста для эмбеддинга и при записи в БД. |
| Надёжность загрузки | Повторы при SSL/таймаутах в hh_client; таймауты (connect/read/write/pool); при ошибке по одной вакансии — пропуск, остальные в чанке обрабатываются. |
| OAuth hh.ru | Настройки в config: `hh_token`, `hh_client_id`, `hh_client_secret`; заголовки Bearer + HH-User-Agent при запросах к API. |
| Frontend | Vue 3 + Vite: дашборд, семантический поиск, RAG (контекст + копирование). GET /stats — агрегаты по rag_vacancies и raw. |
| Деплой frontend | Multi-stage Dockerfile (node build → nginx), nginx proxy /api/ → app:8000, сервис frontend в docker-compose. |
| Навыки | Таблицы `skills` и `vacancy_skills`; сбор из `key_skills` + второй проход по тексту вакансии (KNOWN_HARD_SKILLS, поиск по границам слов). |

---

## 2. Составные части системы

### 2.1 Высокоуровневая схема

```
[hh.ru API] → [Backend: загрузка] → [raw_vacancies]
                    ↓
              [process_raw_to_rag]
                    ↓
[rag_vacancies + embedding] ← [sentence-transformers embed_batch]
                    ↓
[Запрос пользователя] → [embed(query)] → [pgvector: ORDER BY embedding <=> query]
                    ↓
[Топ-N вакансий] → [Формирование context] → [GET /rag] → (опционально) LLM
```

### 2.2 Стек

| Слой | Технология |
|------|------------|
| БД | PostgreSQL 16 + pgvector |
| Backend | Python 3.11, FastAPI |
| Эмбеддинги | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2, 384 dim) |
| Данные | hh.ru API (GET /vacancies, GET /vacancies/{id}) |
| Frontend | Vue 3, Vite |
| Инфра | Docker Compose |

### 2.3 Ключевые модули backend

- **app/config.py** — настройки (DATABASE_URL, EMBEDDING_MODEL, HH_TOKEN и др.).
- **app/db.py** — подключение к PostgreSQL, `register_vector(conn)`, `list_to_pgvector(vec)`.
- **app/embeddings.py** — загрузка модели (lru_cache), `embed(text)`, `embed_batch(texts)`.
- **app/hh_client.py** — запросы к API, `strip_html()`, `vacancy_to_text()`.
- **app/vacancies.py** — upsert raw/rag, `load_and_index_vacancies`, `load_and_index_vacancies_multi`, `process_raw_to_rag`, `search_similar`, `get_stats`.
- **app/skills.py** — сбор навыков из raw (key_skills + поиск по тексту), `get_skills`.
- **app/main.py** — FastAPI: /health, /ingest, /ingest/bulk, /ingest/embed, /search, /rag, /stats, /skills, POST /skills/collect.

---

## 3. Как считается расстояние между векторами

### 3.1 Модель и размерность

- Модель: **paraphrase-multilingual-MiniLM-L12-v2** (sentence-transformers).
- Размерность вектора: **384**.
- Одна и та же модель используется для индекса (вакансии) и для запроса.

### 3.2 Оператор в pgvector

В проекте используется **косинусное расстояние**:

- Оператор pgvector: **`<=>`** (cosine distance).
- Формула: `cosine_distance = 1 - cosine_similarity`.
- Значения расстояния: от 0 (одинаковое направление) до 2 (противоположные). Чем меньше — тем ближе.

### 3.3 Similarity в ответе

Чтобы отдавать пользователю «степень похожести» от 0 до 1 (больше — лучше), в коде считается:

```text
similarity = 1 - (embedding <=> query_vector)
```

То есть из косинусного расстояния получаем косинусное сходство.

### 3.4 SQL поиска (фрагмент из search_similar)

```sql
SELECT hh_id, name, description, employer_name, area_name,
       salary_from, salary_to, url,
       1 - (embedding <=> %s::vector) AS similarity
FROM public.rag_vacancies
ORDER BY embedding <=> %s::vector
LIMIT %s
```

- Сортировка по возрастанию косинусного расстояния → сверху самые близкие.
- В проекте индекс IVFFlat по `embedding` с `vector_cosine_ops` для ускорения такого поиска.

---

## 4. Как получить топ запросов из RAG

### 4.1 Два эндпоинта

- **GET /search?q=...&limit=...** — только семантический поиск: возвращает список вакансий с полями и `similarity`. Используется для поиска по вакансиям.
- **GET /rag?q=...&limit=...** — тот же поиск плюс формирование **контекста** для RAG: топ-N вакансий склеиваются в один текст и возвращаются вместе со списком источников.

### 4.2 Внутренняя логика (как получается топ)

1. Запрос пользователя `q` передаётся в `search_similar(query=q, limit=limit)`.
2. Считается эмбеддинг запроса: `query_vec = embed(query)`.
3. В БД выполняется запрос (см. выше): сортировка по `embedding <=> query_vec`, `LIMIT limit`.
4. Результат — список словарей с полями вакансии и `similarity`.

Для **GET /rag** дополнительно:

5. Для каждой вакансии из топа формируется блок: `[Вакансия N] название — работодатель (регион)\nописание`.
6. Блоки склеиваются через `"\n\n---\n\n"`.
7. В ответе: `query`, `context` (готовый текст для промпта), `sources` (name, url, similarity).

### 4.3 Использование топа в LLM

Контекст из `GET /rag` можно подставить в промпт любой LLM, например:

- «По следующим вакансиям ответь на вопрос. Вакансии: {context}. Вопрос: {query}. Ответ:»
- В коде проекта вызов LLM не реализован — отдаётся только `context` и `sources`.

---

## 5. Проектирование backend

### 5.1 Разделение этапов загрузки

- **Этап 1 (сырые данные):** только сохранение ответа API в `raw_vacancies` (hh_id + raw_json). Без эмбеддингов. Эндпоинты: POST /ingest, POST /ingest/bulk.
- **Этап 2 (RAG-слой):** чтение из `raw_vacancies`, построение текста (`vacancy_to_text`), батч эмбеддингов, запись в `rag_vacancies`. Эндпоинт: POST /ingest/embed.

Так можно пересчитывать эмбеддинги (например, после смены модели или логики `vacancy_to_text`) без повторной выкачки с hh.ru.

### 5.2 Подготовка текста для эмбеддинга

В `vacancy_to_text(v)`:

- Название вакансии.
- Описание без HTML (`strip_html`), обрезка до 3000 символов.
- Строка «Навыки: …» из `key_skills`.

От этого текста напрямую зависит качество семантического поиска.

### 5.3 Обработка ошибок и лимиты API

- В hh_client: повтор запросов при таймауте/SSL; таймауты заданы для connect/read/write/pool.
- При массовой загрузке: чанки по N вакансий, пауза между запросами деталей; при ошибке по одной вакансии — пропуск, остальные в чанке обрабатываются.
- Параметр `search_field` в API hh.ru: допустимы только `name`, `company_name`, `description` (не `all`).

### 5.4 Навыки

- Сбор: POST /skills/collect. Два прохода — из `key_skills` и по тексту вакансии (KNOWN_HARD_SKILLS + уже собранные навыки, поиск по границам слов).
- Список: GET /skills?limit=... — топ навыков с количеством вакансий.

---

## 6. Проектирование frontend

### 6.1 Роли

- **Дашборд** — статистика (GET /stats): число вакансий, работодателей, регионы, зарплаты, сырые вакансии; блок «Вакансии по навыкам» (GET /skills).
- **Поиск** — форма запроса, вызов GET /search, отображение результатов с similarity и ссылками.
- **RAG** — форма запроса, вызов GET /rag, отображение контекста и источников, копирование контекста в буфер.

### 6.2 API и proxy

- Запросы к backend идут на тот же origin или через proxy. В nginx для Docker: `location /api/` с rewrite на `http://app:8000`, чтобы фронт обращался к `/api/search`, `/api/rag` и т.д.
- В frontend используется общий слой запросов (например, `request('/stats')`, `request('/search?q=...')`).

### 6.3 Сборка и деплой

- Frontend: Vue 3 + Vite, сборка в статику; в Docker — multi-stage (node build → nginx), раздача статики + proxy /api/ на backend.

---

## 7. Таблица с embedding и схема БД

### 7.1 Расширение и тип вектора

```sql
CREATE EXTENSION IF NOT EXISTS vector;
-- Колонка: embedding vector(384)
```

Размерность 384 должна совпадать с моделью (MiniLM-L12). При смене модели может потребоваться `ALTER COLUMN embedding TYPE vector(N)` и переиндексация.

### 7.2 Таблицы

**raw_vacancies** (этап выгрузки):

| Колонка   | Тип        | Описание                    |
|-----------|------------|-----------------------------|
| hh_id     | VARCHAR(32)| PK, id вакансии на hh.ru    |
| raw_json  | JSONB      | Полный ответ GET /vacancies/{id} |
| created_at| TIMESTAMPTZ| Время добавления            |

**rag_vacancies** (поиск и RAG):

| Колонка      | Тип         | Описание                          |
|--------------|-------------|-----------------------------------|
| id           | BIGSERIAL   | PK                                |
| hh_id        | VARCHAR(32) | UNIQUE, связь с raw               |
| name         | TEXT        | Название вакансии                 |
| description  | TEXT        | Описание без HTML                 |
| employer_name| TEXT        | Работодатель                      |
| area_name    | TEXT        | Регион                            |
| salary_from  | INTEGER     | Зарплата от                       |
| salary_to    | INTEGER     | Зарплата до                       |
| url          | TEXT        | Ссылка на вакансию                |
| published_at | TIMESTAMPTZ | Дата публикации                   |
| created_at   | TIMESTAMPTZ | Время добавления в RAG            |
| **embedding**| **vector(384)** | Эмбеддинг текста вакансии    |

**skills** — справочник навыков (id, name).  
**vacancy_skills** — связь многие-ко-многим (hh_id, skill_id).

### 7.3 Индекс для векторного поиска

```sql
CREATE INDEX IF NOT EXISTS rag_vacancies_embedding_idx
ON public.rag_vacancies
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

- **ivfflat** — приближённый k-NN; подходит для тысяч/десятков тысяч строк.
- **vector_cosine_ops** — использование косинусного расстояния (`<=>`).

### 7.4 Запись вектора из приложения

Вектор передаётся в SQL как строка JSON-массива с приведением к типу:

- `list_to_pgvector(vec)` формирует строку вида `'[0.1, 0.2, ...]'`.
- В запросе: `%s::vector` (например, в INSERT и в ORDER BY при поиске).

---

## 8. Краткий чеклист по RAG в проекте

- **Одна модель эмбеддингов** для индекса и запросов; размерность = 384, тип колонки `vector(384)`.
- **Расстояние**: косинусное (`<=>`); в ответе — similarity как `1 - distance`.
- **Топ из RAG**: один и тот же `search_similar()`; для /rag поверх результата собирается `context` и `sources`.
- **Backend**: два этапа (raw → rag), отдельный POST /ingest/embed; текст для эмбеддинга — название + описание без HTML + навыки.
- **Frontend**: дашборд (stats + skills), поиск, RAG с копированием контекста; при необходимости proxy /api/ на backend.
- **Навыки**: нет отдельного справочника навыков в API hh.ru; сбор из вакансий (key_skills + поиск по тексту).

Дополнительные детали: [RAG 101](03-rag-101.md), [pgvector 101](02-pgvector-101.md), [Архитектура проекта](04-project-architecture.md), [hh.ru API и индексация](05-hh-api-and-ingest.md).
