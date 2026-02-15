# Frontend RAG HH

Веб-интерфейс на **Vue 3** и **Vite**: дашборд по вакансиям, семантический поиск и RAG-контекст.

## Требования

- **Node.js** 18+ (рекомендуется 20 LTS)
- Запущенный бэкенд API (порт 8001), см. [корневой README](../README.md)

## Установка зависимостей

Из корня проекта:

```bash
cd frontend
npm install
```

Или из любой директории:

```bash
npm install --prefix /path/to/rag-hh/frontend
```

## Запуск в режиме разработки

1. Запустите API (например, `docker compose up` в корне проекта или `uvicorn app.main:app --reload`).
2. В отдельном терминале:

```bash
cd frontend
npm run dev
```

Откроется сервер разработки: **http://localhost:5173**.

- Запросы к API идут через **прокси**: все вызовы на `/api/*` перенаправляются на `http://localhost:8001/*`.
- При изменении кода страница перезагружается автоматически (HMR).

### Если API на другом хосте/порту

Задайте базовый URL API через переменную окружения и запускайте dev без прокси к localhost:

```bash
VITE_API_URL=http://192.168.1.10:8001 npm run dev
```

Тогда запросы пойдут напрямую на указанный URL (убедитесь, что на бэкенде включён CORS для этого origin).

## Сборка (production)

Сборка статики в папку `dist/`:

```bash
cd frontend
npm run build
```

Артефакты появятся в **`frontend/dist/`** (HTML, JS, CSS). Эту папку можно раздавать любым HTTP-сервером (Nginx, Apache, CDN).

### Переменные при сборке

По умолчанию фронтенд обращается к API по относительному пути `/api`. Если в production API на другом домене/порту, укажите полный URL при сборке:

```bash
VITE_API_URL=https://api.example.com npm run build
```

В этом случае на сервере должен быть настроен прокси с `/api` на бэкенд, либо в `VITE_API_URL` задан полный URL бэкенда.

## Просмотр production-сборки локально

После `npm run build` можно посмотреть результат без деплоя:

```bash
npm run preview
```

По умолчанию откроется **http://localhost:4173**. Учтите: в режиме preview запросы идут на тот же хост (относительный `/api`), поэтому для полной проверки API должен быть доступен (например, через прокси или тот же порт).

## Структура проекта

```
frontend/
├── index.html          # Точка входа HTML
├── package.json        # Зависимости и скрипты
├── vite.config.js      # Конфигурация Vite (прокси, алиасы)
├── public/             # Статика без обработки (favicon и т.п.)
│   └── favicon.svg
├── src/
│   ├── main.js         # Инициализация Vue и роутера
│   ├── App.vue         # Корневой компонент (шапка, навигация)
│   ├── style.css       # Глобальные стили и CSS-переменные
│   ├── api.js          # Клиент API (getStats, search, rag, health)
│   ├── router/
│   │   └── index.js    # Маршруты: /, /search, /rag
│   └── views/
│       ├── Dashboard.vue   # Дашборд (статистика, регионы)
│       ├── Search.vue      # Семантический поиск
│       └── Rag.vue         # RAG: контекст и копирование
└── README.md           # Эта документация
```

## Скрипты (package.json)

| Скрипт       | Описание |
|-------------|----------|
| `npm run dev`     | Сервер разработки на http://localhost:5173 с HMR и прокси к API |
| `npm run build`   | Production-сборка в `dist/` |
| `npm run preview` | Локальный просмотр собранного `dist/` (по умолчанию порт 4173) |

## Переменные окружения

| Переменная      | Описание |
|-----------------|----------|
| `VITE_API_URL`  | Базовый URL API. По умолчанию `'/api'` (относительный путь, прокси в dev на 8001). При сборке можно задать полный URL бэкенда. |

Имена переменных должны начинаться с `VITE_`, чтобы попасть в бандл (см. [Vite env](https://vitejs.dev/guide/env-and-mode.html)).

## Развёртывание в Docker

Фронтенд собирается в образ и раздаётся через nginx в том же `docker compose`, что и backend:

```bash
docker compose up --build
```

Откройте http://localhost:3000 — SPA и запросы к API (`/api/*`) проксируются на backend. Сборка: multi-stage Dockerfile в `frontend/`, nginx конфиг в `frontend/nginx.conf`.

## Развёртывание в production (без Docker)

1. Собрать фронтенд: `npm run build`.
2. Раздавать содержимое `frontend/dist/` через веб-сервер.
3. Для SPA настроить fallback на `index.html` (в Nginx: `try_files $uri $uri/ /index.html;`).
4. Если API на другом домене — собрать с `VITE_API_URL=https://...` и настроить CORS на бэкенде.
