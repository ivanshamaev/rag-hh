-- pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Вакансии с hh.ru + вектор эмбеддинга
CREATE TABLE IF NOT EXISTS vacancies (
    id BIGSERIAL PRIMARY KEY,
    hh_id VARCHAR(32) UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    employer_name TEXT,
    area_name TEXT,
    salary_from INTEGER,
    salary_to INTEGER,
    url TEXT,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    embedding vector(384)  -- MiniLM-L12 = 384 dimensions
);

-- Индекс для быстрого приближённого поиска (IVFFlat)
-- lists = 100 — подбирается под объём данных
CREATE INDEX IF NOT EXISTS vacancies_embedding_idx ON vacancies
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Для точного поиска по небольшой коллекции можно использовать только ORDER BY
-- Для больших данных IVFFlat ускоряет поиск в ущерб точности (настраивается lists)

COMMENT ON TABLE vacancies IS 'Вакансии с hh.ru с эмбеддингами для RAG';
