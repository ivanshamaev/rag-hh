"""
Клиент API hh.ru для загрузки вакансий.
Документация: https://dev.hh.ru/
"""
import re
import time
from typing import Any

import httpx

API_BASE = "https://api.hh.ru"


def fetch_vacancies(
    text: str = "python",
    per_page: int = 100,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """
    Поиск вакансий. Без авторизации можно делать до 5 запросов в минуту на один IP.
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
                    "search_field": "name",  # или "all"
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
    if v.get("description"):
        # убираем HTML-теги для краткости
        desc = v["description"]
        for tag in ("<p>", "</p>", "<br>", "<br/>", "<ul>", "</ul>", "<li>", "</li>", "<strong>", "</strong>"):
            desc = desc.replace(tag, " ")
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = " ".join(desc.split())
        parts.append(desc[:3000])  # ограничиваем длину
    if v.get("key_skills"):
        parts.append("Навыки: " + ", ".join(s["name"] for s in v["key_skills"]))
    return "\n".join(parts).strip()
