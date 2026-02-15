#!/usr/bin/env python3
"""
Загрузка вакансий по профессиональным ролям и региону (Москва по умолчанию)
в RAG: список ролей с api.hh.ru → сбор ID вакансий → детали → эмбеддинги → БД.

Токен и при необходимости client_id/client_secret берутся из .env (HH_TOKEN, HH_CLIENT_ID, HH_CLIENT_SECRET)
или из config.json как запасной вариант.

Пример:
  python scripts/ingest_by_roles.py
  python scripts/ingest_by_roles.py --area 1 --max-per-role 500 --roles "Дата-инженер" "Аналитик"
  HH_TOKEN=your_token python scripts/ingest_by_roles.py
"""
import json
import os
import sys
from pathlib import Path

# Корень проекта для импортов
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Токен (и при необходимости client_id, client_secret) из config.json до импорта app
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
if CONFIG_PATH.exists():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("token"):
            os.environ.setdefault("HH_TOKEN", cfg["token"])
        if cfg.get("client_id"):
            os.environ.setdefault("HH_CLIENT_ID", cfg["client_id"])
        if cfg.get("client_secret"):
            os.environ.setdefault("HH_CLIENT_SECRET", cfg["client_secret"])
    except Exception:
        pass


def main() -> None:
    import argparse
    from app.hh_client import fetch_professional_roles, fetch_vacancies_by_role
    from app.vacancies import load_and_index_vacancy_ids

    parser = argparse.ArgumentParser(
        description="Загрузка вакансий по профессиональным ролям (Москва) в RAG"
    )
    parser.add_argument(
        "--area",
        type=int,
        default=1,
        help="Код региона (1 = Москва)",
    )
    parser.add_argument(
        "--max-per-role",
        type=int,
        default=500,
        help="Максимум вакансий на одну роль (по умолчанию 500)",
    )
    parser.add_argument(
        "--roles",
        nargs="*",
        default=None,
        help="Фильтр по названию ролей (подстрока). Без указания — все роли",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=2000,
        help="Максимум уникальных вакансий всего (по умолчанию 2000)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100,
        help="Размер чанка при записи в БД (по умолчанию 100)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Пауза между страницами поиска по роли (сек)",
    )
    parser.add_argument(
        "--detail-delay",
        type=float,
        default=1.2,
        help="Пауза между запросами деталей вакансии (сек)",
    )
    args = parser.parse_args()

    print("Загрузка списка профессиональных ролей...")
    roles = fetch_professional_roles()
    print(f"Всего ролей: {len(roles)}")

    if args.roles:
        roles = [r for r in roles if any(s.lower() in r["name"].lower() for s in args.roles)]
        print(f"После фильтра по названию: {len(roles)} ролей")

    if not roles:
        print("Нет ролей для обработки.")
        return

    seen_ids: set[str] = set()
    all_ids: list[str] = []

    for role in roles:
        if len(all_ids) >= args.target:
            break
        role_id = role["id"]
        role_name = role["name"]
        print(f"  Роль: {role_name} (id={role_id})...", end=" ", flush=True)
        items = fetch_vacancies_by_role(
            role_id,
            area=args.area,
            max_pages=min(20, (args.max_per_role + 99) // 100),
            only_with_salary=False,
            delay_sec=args.delay,
        )
        added = 0
        for it in items:
            if len(all_ids) >= args.target:
                break
            vid = str(it.get("id", ""))
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                all_ids.append(vid)
                added += 1
        print(f"+{added} вакансий (всего {len(all_ids)})")

    to_index = all_ids[: args.target]
    if not to_index:
        print("Нет вакансий для индексации.")
        return

    print(f"\nИндексация {len(to_index)} вакансий (чанки по {args.chunk_size})...")
    n = load_and_index_vacancy_ids(
        to_index,
        chunk_size=args.chunk_size,
        detail_delay_sec=args.detail_delay,
    )
    print(f"Проиндексировано: {n}")


if __name__ == "__main__":
    main()
