-- 142: Фото заданий (C-scope дизайн-аудита Kimi3: «нет фотографий задания»).
-- До 3 фото на задание; отдаются с /uploads/jobs/... (public GET, как аватары).

ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS photo_urls text[] NOT NULL DEFAULT '{}';

-- Публичное чтение (RLS jobs SELECT уже по статусу open/completed/cancelled)
GRANT SELECT (photo_urls) ON public.jobs TO authenticated;
GRANT SELECT (photo_urls) ON public.jobs TO anon;
GRANT UPDATE (photo_urls) ON public.jobs TO authenticated;
GRANT SELECT (photo_urls) ON public.jobs TO service_role;

NOTIFY pgrst, 'reload schema';
