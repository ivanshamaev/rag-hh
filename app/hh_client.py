"""
Клиент API hh.ru для загрузки вакансий.
Документация: https://dev.hh.ru/
"""
import re
import time
from typing import Any

import httpx

API_BASE = "https://api.hh.ru"

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
    """Получить полное описание вакансии по id."""
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{API_BASE}/vacancies/{vacancy_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


def vacancy_to_text(v: dict[str, Any]) -> str:
    """Собрать текст вакансии для эмбеддинга: название + описание + требования."""
    parts = [v.get("name", "")]
    desc = strip_html(v.get("description"))
    if desc:
        parts.append(desc[:3000])  # ограничиваем длину
    if v.get("key_skills"):
        parts.append("Навыки: " + ", ".join(s["name"] for s in v["key_skills"]))
    return "\n".join(parts).strip()
