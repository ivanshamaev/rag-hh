-- Добавить колонку с полным ответом API hh.ru (для БД, созданных до этого изменения)
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS hh_response JSONB;
COMMENT ON COLUMN vacancies.hh_response IS 'Полный ответ API hh.ru GET /vacancies/{id}';
