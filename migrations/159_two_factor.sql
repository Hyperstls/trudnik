-- 159: Двухэтапный вход — email-код как второй фактор.
--
-- profiles.two_factor_enabled=false (по умолчанию) — вход по паролю не меняется.
-- true — после успешного пароля Django-флоу не создаёт authenticated-сессию,
-- а отправляет 6-значный код на email и завершает вход только после ввода кода.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS two_factor_enabled boolean NOT NULL DEFAULT false;

-- PostgREST-доступ (паритет с worker_visibility из 140): флаг читает и
-- переключает сам пользователь, service_role — служебные проверки.
GRANT SELECT (two_factor_enabled) ON public.profiles TO authenticated;
GRANT UPDATE (two_factor_enabled) ON public.profiles TO authenticated;
GRANT SELECT (two_factor_enabled) ON public.profiles TO service_role;

NOTIFY pgrst, 'reload schema';
