-- 152: remote jobs flag.
--
-- Additive column for remote work; existing jobs default to offline.
ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS is_remote boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_jobs_remote_open
    ON public.jobs (is_remote)
    WHERE status = 'open';
