CREATE TABLE IF NOT EXISTS public.skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);
COMMENT ON TABLE public.skills IS 'Справочник навыков (нормализованное имя)';

CREATE TABLE IF NOT EXISTS public.vacancy_skills (
    hh_id VARCHAR(32) NOT NULL,
    skill_id INTEGER NOT NULL REFERENCES public.skills(id) ON DELETE CASCADE,
    PRIMARY KEY (hh_id, skill_id)
);
CREATE INDEX IF NOT EXISTS vacancy_skills_skill_id_idx ON public.vacancy_skills(skill_id);
COMMENT ON TABLE public.vacancy_skills IS 'Связь вакансия — навык (hh_id из raw_vacancies)';
