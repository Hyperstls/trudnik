-- Миграция: справочники навыков и вероисповеданий
-- Дата: 2026-06-07

-- 1. Справочник навыков
CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Справочник вероисповеданий
CREATE TABLE IF NOT EXISTS religions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Связь пользователь-навыки (трудники)
CREATE TABLE IF NOT EXISTS user_skills (
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, skill_id)
);

-- 4. Связь задание-навыки
CREATE TABLE IF NOT EXISTS job_skills (
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, skill_id)
);

-- 5. Добавляем religion_id в profiles (опционально, FK)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS religion_id UUID REFERENCES religions(id) ON DELETE SET NULL;

-- 6. Предзаполняем справочники базовыми значениями
INSERT INTO religions (name) VALUES
    ('Православие'),
    ('Ислам'),
    ('Буддизм'),
    ('Иудаизм'),
    ('Католичество'),
    ('Протестантизм'),
    ('Новые религиозные движения')
ON CONFLICT (name) DO NOTHING;

INSERT INTO skills (name) VALUES
    ('IT'),
    ('Бухгалтер'),
    ('Водитель'),
    ('Кровельщик'),
    ('Маляр'),
    ('Охрана'),
    ('Плиточник'),
    ('Плотник'),
    ('Повар'),
    ('Разгрузка'),
    ('Разнорабочий'),
    ('Садоводство'),
    ('Сантехник'),
    ('Сварщик'),
    ('Секретарь'),
    ('Столяр'),
    ('Уборка'),
    ('Уход за животными'),
    ('Штукатур'),
    ('Электрик'),
    ('Автомеханик'),
    ('Выгул собак'),
    ('Грузчик'),
    ('Дизайн'),
    ('IT поддержка'),
    ('Курьер'),
    ('Переводы'),
    ('Покраска'),
    ('Присмотр за детьми'),
    ('Ремонт'),
    ('Репетиторство'),
    ('Сантехника'),
    ('Строительство'),
    ('Фото/видео'),
    ('Швея'),
    ('Электрика')
ON CONFLICT (name) DO NOTHING;

-- 7. RLS
ALTER TABLE skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE religions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_skills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "read_skills" ON skills FOR SELECT USING (true);
CREATE POLICY "read_religions" ON religions FOR SELECT USING (true);
CREATE POLICY "read_user_skills" ON user_skills FOR SELECT USING (true);
CREATE POLICY "read_job_skills" ON job_skills FOR SELECT USING (true);

CREATE POLICY "admin_skills" ON skills FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "admin_religions" ON religions FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "user_own_skills" ON user_skills FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "employer_job_skills" ON job_skills FOR ALL
    USING (EXISTS (SELECT 1 FROM jobs WHERE id = job_id AND employer_id = auth.uid()));
