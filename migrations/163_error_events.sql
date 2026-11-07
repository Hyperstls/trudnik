-- 163: error_events — внутренний error tracking (R039).
--
-- Только технический минимум для разбора 500: тип исключения, путь без query,
-- метод, user_id и file:line-фреймы. Текст ошибки, тело запроса, заголовки,
-- query string и PII не сохраняются (152-ФЗ, отказ от внешнего Sentry).
-- Идемпотентно.

CREATE TABLE IF NOT EXISTS public.error_events (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    exception_type  varchar(200) NOT NULL,
    path            varchar(500) NOT NULL,
    method          varchar(10) NOT NULL,
    status_code     integer NOT NULL DEFAULT 500,
    user_id         uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
    frames          jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS error_events_created_at_idx
    ON public.error_events (created_at DESC);

GRANT SELECT, INSERT, DELETE ON public.error_events TO trudnik_dj;
