-- pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Этап 1: сырые данные из API hh.ru (только id + json)
CREATE TABLE IF NOT EXISTS public.raw_vacancies (
    hh_id VARCHAR(32) PRIMARY KEY,
    raw_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE public.raw_vacancies IS 'Сырые ответы API hh.ru (GET /vacancies/{id}); этап выгрузки без эмбеддингов';

-- Этап 2: вакансии с эмбеддингами для RAG (поиск, дашборд)
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
    embedding vector(384)  -- MiniLM-L12 = 384 dimensions
);
CREATE INDEX IF NOT EXISTS rag_vacancies_embedding_idx ON public.rag_vacancies
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
COMMENT ON TABLE public.rag_vacancies IS 'Вакансии с эмбеддингами для RAG; заполняется из raw_vacancies';

-- Навыки по вакансиям (из raw_vacancies.raw_json.key_skills)
CREATE TABLE IF NOT EXISTS public.skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);
COMMENT ON TABLE public.skills IS 'Справочник навыков (нормализованное имя, например python, sql)';

CREATE TABLE IF NOT EXISTS public.vacancy_skills (
    hh_id VARCHAR(32) NOT NULL REFERENCES public.raw_vacancies(hh_id) ON DELETE CASCADE,
    skill_id INTEGER NOT NULL REFERENCES public.skills(id) ON DELETE CASCADE,
    PRIMARY KEY (hh_id, skill_id)
);
CREATE INDEX IF NOT EXISTS vacancy_skills_skill_id_idx ON public.vacancy_skills(skill_id);
COMMENT ON TABLE public.vacancy_skills IS 'Связь вакансия — навык (многие ко многим)';
