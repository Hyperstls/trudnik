-- Миграция: добавление sort_order для навыков и вероисповеданий
-- Дата: 2026-06-08
-- Позволяет админу задавать порядок отображения в списках

-- 1. Добавляем sort_order в skills
ALTER TABLE skills ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;

-- 2. Добавляем sort_order в religions
ALTER TABLE religions ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;

-- 3. Обновляем существующие записи: задаём порядок по алфавиту
UPDATE skills SET sort_order = sub.rn
FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY name) AS rn FROM skills) sub
WHERE skills.id = sub.id;

UPDATE religions SET sort_order = sub.rn
FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY name) AS rn FROM religions) sub
WHERE religions.id = sub.id;

-- 4. Индексы для быстрой сортировки
CREATE INDEX IF NOT EXISTS idx_skills_sort ON skills(sort_order, name);
CREATE INDEX IF NOT EXISTS idx_religions_sort ON religions(sort_order, name);
