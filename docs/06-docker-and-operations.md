# Docker и эксплуатация

Как поднять проект в Docker, какие переменные окружения использовать и как решать типичные задачи при разработке и запуске.

---

## 1. Состав Docker Compose

В `docker-compose.yml` два сервиса:

- **db** — PostgreSQL 16 с расширением pgvector (образ `pgvector/pgvector:pg16`). Порт 5432, volume для данных, healthcheck. При первом запуске выполняется `db/init.sql` из `docker-entrypoint-initdb.d`.
- **app** — приложение на FastAPI. Собирается из `Dockerfile`, подключается к БД по имени сервиса `db`, порт приложения проброшен на хост (например 8001:8000).

Приложение ждёт готовности БД через `depends_on: db: condition: service_healthy`.

---

## 2. Запуск

Из корня репозитория:

```bash
docker compose up --build
```

- Первый раз: сборка образа app (установка Python-зависимостей, в т.ч. CPU-only torch и sentence-transformers), создание volume и БД, выполнение `init.sql`.
- В логах db должно появиться сообщение о создании расширения и таблицы; app — о старте uvicorn.

Остановка: `Ctrl+C` или `docker compose down`. Данные БД сохраняются в volume `rag-hh_pgdata` (или как назван volume в compose).

Порт приложения: в текущей конфигурации **8001** на хосте (чтобы не конфликтовать с занятым 8000). API: http://localhost:8001, Swagger: http://localhost:8001/docs.

---

## 3. Переменные окружения

### app-сервис

| Переменная | Описание | По умолчанию в compose |
|------------|----------|-------------------------|
| `DATABASE_URL` | Строка подключения к PostgreSQL | `postgresql://rag:rag@db:5432/rag_hh` |
| `EMBEDDING_MODEL` | Имя модели sentence-transformers | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |

Для локального запуска приложения без Docker (при этом БД может быть в Docker) задайте `DATABASE_URL` с хостом `localhost`, например:

```bash
export DATABASE_URL=postgresql://rag:rag@localhost:5432/rag_hh
```

Файл `.env.example` содержит примеры; скопируйте в `.env` и при необходимости измените (в репозитории `.env` в git не попадает).

### db-сервис

В compose заданы `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (rag, rag, rag_hh). Менять их нужно согласованно с `DATABASE_URL` в app.

---

## 4. Dockerfile приложения (кратко)

- Базовый образ: `python:3.11-slim`.
- Установка `build-essential` для сборки части зависимостей.
- Установка **torch** из CPU-only индекса (чтобы образ был меньше и быстрее собирался), затем `pip install -r requirements.txt`.
- Рабочая директория `/app`, копирование кода, порт 8000.
- В режиме dev через compose используется `command: uvicorn ... --reload` и монтирование текущего каталога в `/app`.

При смене модели эмбеддингов достаточно поменять `EMBEDDING_MODEL`; если новая модель требует другую размерность — нужна миграция БД (тип колонки `vector(N)` и переиндексация).

---

## 5. Типичные задачи

### Проверить, что БД и pgvector работают

Подключиться к контейнеру БД и выполнить:

```bash
docker compose exec db psql -U rag -d rag_hh -c "SELECT COUNT(*) FROM vacancies;"
docker compose exec db psql -U rag -d rag_hh -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

### Первая индексация

После старта контейнеров:

1. Открыть http://localhost:8001/docs.
2. Вызвать **POST /ingest** с телом, например: `{"search_query": "python", "max_vacancies": 30}`.
3. Дождаться ответа (первый раз дольше — загрузка модели эмбеддингов).

После этого можно вызывать **GET /search** и **GET /rag**.

### Логи приложения

```bash
docker compose logs -f app
```

### Пересоздать БД с нуля

```bash
docker compose down -v
docker compose up -d db
# дождаться health
docker compose up -d app
```

Флаг `-v` удаляет volumes, в т.ч. данные PostgreSQL. После этого снова выполнится `init.sql` при старте db.

### Запуск только БД (приложение локально)

```bash
docker compose up -d db
```

В другом терминале на хосте:

```bash
cd /path/to/rag-hh
pip install -r requirements.txt
# при необходимости: pip install torch (или CPU-версия torch)
export DATABASE_URL=postgresql://rag:rag@localhost:5432/rag_hh
uvicorn app.main:app --reload --port 8000
```

Убедитесь, что порт 5432 не занят другим PostgreSQL на хосте.

---

## 6. На что обратить внимание

- **Первый запрос к /ingest или /search** — долгий из-за загрузки модели sentence-transformers в память.
- **IVFFlat-индекс** создаётся при пустой/маленькой таблице; в логах db может быть NOTICE про low recall. После накопления достаточного числа строк индекс можно пересоздать с большим `lists` (см. [pgvector 101](02-pgvector-101.md)).
- **Лимиты hh.ru**: при частой индексации соблюдайте паузы в коде и не превышайте лимиты API.

С этой конфигурацией можно стабильно разрабатывать и тестировать RAG HH; для продакшена дополнительно имеет смысл вынести секреты в безопасное хранилище и при необходимости настроить ресурсы контейнеров (memory/CPU limits).
