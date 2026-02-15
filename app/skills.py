"""
Сбор навыков из сырых вакансий: key_skills + поиск по названию и описанию (глубокий анализ).
"""
import json
import re
from typing import Any

import psycopg

from app.db import get_connection_sync
from app.hh_client import strip_html

# Дополнительные технические навыки для поиска в тексте вакансии (если нет в key_skills)
# Формат: нормализованное имя (lowercase). Многословные — целиком, например "apache nifi"
KNOWN_HARD_SKILLS = [
    "python", "sql", "java", "scala", "kotlin", "go", "golang", "rust", "c++", "c#", "javascript", "typescript",
    "spark", "apache spark", "kafka", "airflow", "apache airflow", "apache nifi", "nifi", "dbt", "airbyte",
    "docker", "kubernetes", "k8s", "terraform", "ansible", "linux", "git", "ci/cd", "jenkins", "gitlab",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "ml", "machine learning", "etl", "elt",
    "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch", "greenplum", "clickhouse",
    "snowflake", "redshift", "bigquery", "tableau", "power bi", "metabase", "superset", "apache superset",
    "hadoop", "hive", "presto", "trino", "dbt core", "dagster", "prefect", "luigi",
    "aws", "gcp", "azure", "yandex cloud", "databricks", "mlflow", "kubeflow",
    "vertica", "exasol", "teradata", "oracle", "sql server", "microsoft sql server",
    "redis", "cassandra", "hbase", "druid", "pinot",

    # Data Warehouse & Modeling
    "data warehouse", "dwh", "data mart", "data lake", "data lakehouse",
    "medallion architecture", "dimensional modeling", "kimball", "inmon",
    "data vault", "data vault 2.0", "star schema", "snowflake schema",
    "fact tables", "dimension tables", "slowly changing dimensions", "scd",
    "surrogate keys", "cdc", "change data capture", "ods",
    "master data management", "mdm", "data governance", "data lineage",
    "data quality", "data modeling",

    # Big Data Frameworks
    "flink", "apache flink", "beam", "apache beam",
    "storm", "apache storm", "samza",
    "hbase", "cassandra", "druid", "pinot",
    "delta lake", "apache iceberg", "iceberg",
    "apache hudi", "hudi",

    # Streaming & Messaging
    "kafka streams", "ksqldb", "debezium",
    "schema registry", "event-driven architecture",
    "stream processing", "real-time data",
    "exactly-once semantics", "idempotent processing",

    # AWS Data Stack
    "aws glue", "aws emr", "aws athena",
    "aws lake formation", "aws kinesis",
    "aws dynamodb", "aws s3",
    "aws redshift spectrum", "aws step functions",

    # GCP Data Stack
    "dataflow", "dataproc", "pub/sub",
    "biglake", "cloud composer",
    "cloud functions", "cloud storage",

    # Azure Data Stack
    "azure data factory", "azure synapse",
    "azure event hub", "azure databricks",
    "azure data lake storage",

    # OLAP & Performance
    "olap", "olap cubes", "columnar storage",
    "materialized views", "partitioning",
    "clustering", "query optimization",
    "cost-based optimizer", "mpp",
    "vectorized execution",

    # Data Formats
    "parquet", "orc", "avro", "jsonl",
    "data compression", "snappy", "zstd", "gzip",

    # Data Quality & Observability
    "great expectations", "data observability",
    "data contracts", "anomaly detection",
    "sla", "slo", "reconciliation",

    # DevOps for Data
    "gitops", "helm", "argo workflows",
    "argocd", "infrastructure as code",
    "blue/green deployment", "canary release",

    # BI & Semantic Layer
    "semantic layer", "metrics layer",
    "cube.dev", "looker", "lookml",

    # Security
    "row level security", "column level security",
    "iam", "data masking",
    "encryption at rest", "encryption in transit",

    # Distributed Systems Concepts
    "distributed systems", "cap theorem",
    "eventual consistency", "data sharding",
    "replication", "consensus algorithms",
    "acid", "base", "transactional lake",
]



def normalize_skill_name(name: str) -> str:
    """Нормализация названия навыка: lowercase, обрезка пробелов, схлопывание пробелов."""
    if not name or not isinstance(name, str):
        return ""
    s = " ".join(name.strip().lower().split())
    return s[:255]  # ограничение по колонке


def _skill_matches_text(skill_name: str, text: str) -> bool:
    """Проверка, что навык упоминается в тексте (целое слово или фраза)."""
    if not skill_name or not text:
        return False
    text_lower = text.lower()
    if " " in skill_name:
        return skill_name in text_lower
    # Одно слово — по границам слова, чтобы не ловить "python" в "pythonic"
    pattern = r"\b" + re.escape(skill_name) + r"\b"
    return bool(re.search(pattern, text_lower))


def _build_vacancy_text(raw: dict[str, Any]) -> str:
    """Текст вакансии для поиска навыков: название + описание без HTML."""
    parts = []
    if raw.get("name"):
        parts.append(str(raw["name"]))
    desc = raw.get("description")
    if desc:
        clean = strip_html(desc)
        if clean:
            parts.append(clean)
    return " ".join(parts)


def collect_skills_from_raw() -> dict[str, Any]:
    """
    Двухэтапный сбор навыков:
    1) key_skills из API;
    2) поиск по названию и описанию вакансии (KNOWN_HARD_SKILLS + уже известные навыки).
    Заполняет public.skills и public.vacancy_skills.
    """
    conn = get_connection_sync()
    try:
        cur = conn.execute("SELECT hh_id, raw_json FROM public.raw_vacancies")
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return {
            "skills_added": 0,
            "vacancy_skills_added": 0,
            "vacancy_skills_from_text": 0,
            "vacancies_processed": 0,
        }

    # Этап 1: key_skills
    vacancy_skill_names: list[tuple[str, set[str]]] = []
    all_names: set[str] = set()
    raw_by_id: dict[str, dict] = {}

    for hh_id, raw_json in rows:
        raw = raw_json if isinstance(raw_json, dict) else json.loads(raw_json)
        raw_by_id[hh_id] = raw
        key_skills = raw.get("key_skills") or []
        names = set()
        for s in key_skills:
            if isinstance(s, dict) and s.get("name"):
                n = normalize_skill_name(s["name"])
                if n:
                    names.add(n)
                    all_names.add(n)
            elif isinstance(s, str):
                n = normalize_skill_name(s)
                if n:
                    names.add(n)
                    all_names.add(n)
        if names:
            vacancy_skill_names.append((hh_id, names))

    # Добавить известные hard skills в справочник (для поиска по тексту)
    for name in KNOWN_HARD_SKILLS:
        n = normalize_skill_name(name)
        if n:
            all_names.add(n)

    conn = get_connection_sync()
    try:
        for name in sorted(all_names):
            conn.execute(
                "INSERT INTO public.skills (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (name,),
            )
        conn.commit()

        conn.execute("DELETE FROM public.vacancy_skills")
        conn.commit()

        cur = conn.execute("SELECT id, name FROM public.skills")
        name_to_id = {r[1]: r[0] for r in cur.fetchall()}

        # Связи из key_skills
        from_key_skills = 0
        for hh_id, names in vacancy_skill_names:
            for name in names:
                skill_id = name_to_id.get(name)
                if skill_id is not None:
                    try:
                        conn.execute(
                            "INSERT INTO public.vacancy_skills (hh_id, skill_id) VALUES (%s, %s) ON CONFLICT (hh_id, skill_id) DO NOTHING",
                            (hh_id, skill_id),
                        )
                        from_key_skills += 1
                    except Exception:
                        pass

        # Этап 2: поиск по названию и описанию (сначала длинные фразы, чтобы не дублировать)
        skill_names_sorted = sorted(name_to_id.keys(), key=len, reverse=True)
        from_text = 0
        for hh_id, raw in raw_by_id.items():
            text = _build_vacancy_text(raw)
            if not text:
                continue
            for skill_name in skill_names_sorted:
                if not _skill_matches_text(skill_name, text):
                    continue
                skill_id = name_to_id.get(skill_name)
                if skill_id is None:
                    continue
                try:
                    conn.execute(
                        "INSERT INTO public.vacancy_skills (hh_id, skill_id) VALUES (%s, %s) ON CONFLICT (hh_id, skill_id) DO NOTHING",
                        (hh_id, skill_id),
                    )
                    from_text += 1
                except Exception:
                    pass

        conn.commit()
        return {
            "skills_added": len(all_names),
            "vacancy_skills_added": from_key_skills + from_text,
            "vacancy_skills_from_key_skills": from_key_skills,
            "vacancy_skills_from_text": from_text,
            "vacancies_processed": len(rows),
            "skills_total": len(name_to_id),
        }
    finally:
        conn.close()


def get_skills(limit: int = 200) -> list[dict[str, Any]]:
    """
    Список навыков с количеством вакансий (топ по частоте).
    """
    conn = get_connection_sync()
    try:
        cur = conn.execute(
            """
            SELECT s.id, s.name, COUNT(vs.hh_id) AS vacancy_count
            FROM public.skills s
            LEFT JOIN public.vacancy_skills vs ON vs.skill_id = s.id
            GROUP BY s.id, s.name
            ORDER BY vacancy_count DESC, s.name
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {"id": r[0], "name": r[1], "vacancy_count": r[2]}
            for r in rows
        ]
    finally:
        conn.close()
