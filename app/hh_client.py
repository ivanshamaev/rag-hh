"""
Клиент API hh.ru для загрузки вакансий.
Документация: https://dev.hh.ru/
"""
import re
import ssl
import time
from typing import Any

import httpx

from app.config import settings

API_BASE = "https://api.hh.ru"


def _get_headers() -> dict[str, str]:
    """Заголовки для запросов к API. Если задан HH_TOKEN — используется авторизация (выше лимиты)."""
    h: dict[str, str] = {}
    if settings.hh_token:
        h["Authorization"] = f"Bearer {settings.hh_token}"
        h["HH-User-Agent"] = settings.hh_user_agent
    return h

# Повторы при сбоях соединения/SSL/таймауте (api.hh.ru иногда обрывает при лимитах)
FETCH_DETAIL_RETRIES = 4
FETCH_DETAIL_RETRY_DELAY_SEC = 3.0
# Таймаут: отдельно на handshake и чтение (handshake часто падает при нагрузке)
FETCH_DETAIL_TIMEOUT = httpx.Timeout(connect=25.0, read=40.0, write=40.0, pool=10.0)

# Максимум вакансий на одну страницу в API hh.ru (GET /vacancies)
PER_PAGE_MAX = 100


def fetch_vacancies(
    text: str = "python",
    per_page: int = PER_PAGE_MAX,
    max_pages: int = 5,
    search_field: str = "name",
) -> list[dict[str, Any]]:
    """
    Поиск вакансий. Без авторизации можно делать до 5 запросов в минуту на один IP.
    per_page: до PER_PAGE_MAX (100) — максимум на страницу.
    search_field: по API hh.ru допустимы name, company_name, description (см. /dictionaries).
    """
    all_items = []
    page = 0

    with httpx.Client(timeout=30.0) as client:
        while page < max_pages:
            r = client.get(
                f"{API_BASE}/vacancies",
                params={
                    "text": text,
                    "per_page": per_page,
                    "page": page,
                    "search_field": search_field,
                },
                headers=_get_headers(),
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("items", [])
            if not items:
                break
            all_items.extend(items)
            if data.get("pages", 0) <= page + 1:
                break
            page += 1
            time.sleep(1.2)  # вежливость к API (ограничение по RPS)

    return all_items


def fetch_professional_roles() -> list[dict[str, Any]]:
    """Список профессиональных ролей (категории и роли) с api.hh.ru/professional_roles."""
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{API_BASE}/professional_roles", headers=_get_headers())
        r.raise_for_status()
        data = r.json()
    roles = []
    for group in data.get("categories", []):
        for role in group.get("roles", []):
            roles.append({"id": role["id"], "name": role["name"]})
    return roles


def fetch_vacancies_by_role(
    role_id: str,
    area: int = 1,
    per_page: int = PER_PAGE_MAX,
    max_pages: int = 20,
    only_with_salary: bool = False,
    delay_sec: float = 0.2,
) -> list[dict[str, Any]]:
    """
    Поиск вакансий по профессиональной роли и региону (как в старом парсере).
    area=1 — Москва. only_with_salary=True — только с зарплатой, сортировка по убыванию.
    """
    all_items = []
    with httpx.Client(timeout=30.0) as client:
        for page in range(max_pages):
            params: dict[str, Any] = {
                "professional_role": role_id,
                "area": area,
                "per_page": per_page,
                "page": page,
            }
            if only_with_salary:
                params["only_with_salary"] = True
                params["order_by"] = "salary_desc"
            r = client.get(f"{API_BASE}/vacancies", headers=_get_headers(), params=params)
            r.raise_for_status()
            data = r.json()
            items = data.get("items", [])
            if not items:
                break
            all_items.extend(items)
            if page >= data.get("pages", 0) - 1:
                break
            time.sleep(delay_sec)
    return all_items


def strip_html(html: str | None) -> str | None:
    """
    Удаление HTML-тегов из строки (описание вакансии с hh.ru).
    Возвращает None для пустого ввода, иначе текст без тегов с нормализованными пробелами.
    """
    if not html or not html.strip():
        return None
    text = html
    for tag in ("<p>", "</p>", "<br>", "<br/>", "<br />", "<ul>", "</ul>", "<li>", "</li>", "<strong>", "</strong>", "<div>", "</div>"):
        text = text.replace(tag, " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text.strip() or None


def fetch_vacancy_detail(vacancy_id: str) -> dict[str, Any] | None:
    """Получить полное описание вакансии по id. При SSL/таймауте/сетевых сбоях — повтор с задержкой."""
    last_error: Exception | None = None
    for attempt in range(FETCH_DETAIL_RETRIES):
        try:
            with httpx.Client(timeout=FETCH_DETAIL_TIMEOUT) as client:
                r = client.get(f"{API_BASE}/vacancies/{vacancy_id}", headers=_get_headers())
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
        except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException, OSError, ssl.SSLError) as e:
            last_error = e
            if attempt < FETCH_DETAIL_RETRIES - 1:
                time.sleep(FETCH_DETAIL_RETRY_DELAY_SEC * (attempt + 1))
            else:
                raise
    if last_error:
        raise last_error
    return None


def vacancy_to_text(v: dict[str, Any]) -> str:
    """Собрать текст вакансии для эмбеддинга: название + описание + требования."""
    parts = [v.get("name", "")]
    desc = strip_html(v.get("description"))
    if desc:
        parts.append(desc[:3000])  # ограничиваем длину
    if v.get("key_skills"):
        parts.append("Навыки: " + ", ".join(s["name"] for s in v["key_skills"]))
    return "\n".join(parts).strip()
