-- Разделение на этап выгрузки (raw) и этап эмбеддингов (rag)
CREATE TABLE IF NOT EXISTS public.raw_vacancies (
    hh_id VARCHAR(32) PRIMARY KEY,
    raw_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE public.raw_vacancies IS 'Сырые ответы API hh.ru; этап выгрузки без эмбеддингов';

CREATE TABLE IF NOT EXISTS public.rag_vacancies (
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
    embedding vector(384)
);
CREATE INDEX IF NOT EXISTS rag_vacancies_embedding_idx ON public.rag_vacancies
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
COMMENT ON TABLE public.rag_vacancies IS 'Вакансии с эмбеддингами для RAG; заполняется из raw_vacancies';
