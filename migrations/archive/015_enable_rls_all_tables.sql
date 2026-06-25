-- ============================================================
-- Миграция: принудительно включить RLS на всех публичных таблицах
-- Исправляет уведомление Supabase: "Table publicly accessible"
-- Выполнить в Supabase SQL Editor
-- ============================================================

ALTER TABLE IF EXISTS public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.shifts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.job_favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.blacklists ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.ratings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.religions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.user_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.job_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.job_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.contact_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.hires ENABLE ROW LEVEL SECURITY;
