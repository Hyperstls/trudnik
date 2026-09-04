-- 140: Мультирольность — флаг видимости в каталоге трудников.
--
-- Семантика: worker_visibility=true → пользователь показывается в каталоге
-- трудников (/workers) и может получать приглашения. false → пользователь
-- только размещает задания и нанимает (не находится поиском, приглашения
-- не приходят), но откликаться/создавать задания может как любой другой.
--
-- Роль (profiles.role) остаётся «ориентацией» (лендинг после логина),
-- доступ определяется владением (RLS/RPC уже роль-агностичны).

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS worker_visibility boolean NOT NULL DEFAULT true;

-- Обратная совместимость: все существующие пользователи видны, как раньше
-- (каталог раньше строился по role='worker'; employer'ы по умолчанию тоже
-- получают true — они теперь могут подрабатывать без второго аккаунта).
DO $$
BEGIN
    UPDATE public.profiles
       SET worker_visibility = true
     WHERE worker_visibility IS NULL;
END $$;

-- Column-level GRANT: SELECT публичным полям уже покрывает новая колонка
-- через "избирательный GRANT" миграции 132? Нет — 132 ограничивала список
-- колонок явно. Добавляем worker_visibility в публичный SELECT/UPDATE.
GRANT SELECT (worker_visibility) ON public.profiles TO authenticated;
GRANT UPDATE (worker_visibility) ON public.profiles TO authenticated;
GRANT SELECT (worker_visibility) ON public.profiles TO service_role;

NOTIFY pgrst, 'reload schema';
