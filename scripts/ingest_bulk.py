#!/usr/bin/env python3
"""
Скрипт массовой загрузки вакансий (Data Engineer и др.) в RAG.
Запуск без поднятия API, с прогрессом в консоль.

Пример:
  python scripts/ingest_bulk.py
  python scripts/ingest_bulk.py --target 500
  python scripts/ingest_bulk.py --queries "data engineer" "dwh"
"""
import argparse
import sys

# чтобы импортировать app при запуске из корня проекта
sys.path.insert(0, ".")


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузка вакансий по нескольким запросам в RAG (дедупликация по id)")
    parser.add_argument(
        "--target",
        type=int,
        default=1000,
        help="Целевое количество уникальных вакансий (по умолчанию 1000)",
    )
    parser.add_argument(
        "--queries",
        nargs="*",
        default=None,
        help="Поисковые запросы (если не заданы — используются ключевые слова Data Engineer)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.2,
        help="Пауза между запросами деталей к API hh.ru в секундах (по умолчанию 1.2)",
    )
    args = parser.parse_args()

    from app.vacancies import DEFAULT_DATA_ENGINEER_QUERIES, load_and_index_vacancies_multi

    queries = args.queries or DEFAULT_DATA_ENGINEER_QUERIES
    print(f"Запросы: {queries}")
    print(f"Цель: {args.target} вакансий, задержка между запросами: {args.delay} с")
    print("Загрузка может занять 20–40 минут из-за лимитов API hh.ru...")

    n = load_and_index_vacancies_multi(
        search_queries=queries,
        target_count=args.target,
        detail_delay_sec=args.delay,
    )
    print(f"Проиндексировано вакансий: {n}")


if __name__ == "__main__":
    main()
