-- ============================================================
-- Миграция: исправление INFO-level performance warnings
-- 1. unindexed_foreign_keys — добавить индексы на FK-колонки
-- 2. unused_index — удалить неиспользуемые индексы
-- Выполнить в Supabase SQL Editor
-- ============================================================

-- ============================================================
-- 1. unindexed_foreign_keys: индексы на внешние ключи
-- ============================================================

-- applications
CREATE INDEX IF NOT EXISTS idx_applications_contact_payment_id ON public.applications(contact_payment_id);
CREATE INDEX IF NOT EXISTS idx_applications_worker_id ON public.applications(worker_id);

-- blacklists
CREATE INDEX IF NOT EXISTS idx_blacklists_blocked_user_id ON public.blacklists(blocked_user_id);

-- contact_payments
CREATE INDEX IF NOT EXISTS idx_contact_payments_application_id ON public.contact_payments(application_id);

-- favorites
CREATE INDEX IF NOT EXISTS idx_favorites_target_id ON public.favorites(target_id);

-- hires
CREATE INDEX IF NOT EXISTS idx_hires_job_id ON public.hires(job_id);
CREATE INDEX IF NOT EXISTS idx_hires_shift_id ON public.hires(shift_id);
CREATE INDEX IF NOT EXISTS idx_hires_worker_id ON public.hires(worker_id);

-- job_favorites
CREATE INDEX IF NOT EXISTS idx_job_favorites_job_id ON public.job_favorites(job_id);

-- job_photos
CREATE INDEX IF NOT EXISTS idx_job_photos_job_id ON public.job_photos(job_id);

-- job_skills
CREATE INDEX IF NOT EXISTS idx_job_skills_skill_id ON public.job_skills(skill_id);

-- messages
CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON public.messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_shift_id ON public.messages(shift_id);

-- profiles
CREATE INDEX IF NOT EXISTS idx_profiles_religion_id ON public.profiles(religion_id);

-- push_subscriptions
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id ON public.push_subscriptions(user_id);

-- ratings
CREATE INDEX IF NOT EXISTS idx_ratings_shift_id ON public.ratings(shift_id);

-- receipts
CREATE INDEX IF NOT EXISTS idx_receipts_contact_payment_id ON public.receipts(contact_payment_id);

-- reviews
CREATE INDEX IF NOT EXISTS idx_reviews_reviewee_id ON public.reviews(reviewee_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer_id ON public.reviews(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_shift_id ON public.reviews(shift_id);

-- shifts
CREATE INDEX IF NOT EXISTS idx_shifts_employer_id ON public.shifts(employer_id);
CREATE INDEX IF NOT EXISTS idx_shifts_job_id ON public.shifts(job_id);
CREATE INDEX IF NOT EXISTS idx_shifts_worker_id ON public.shifts(worker_id);

-- user_skills
CREATE INDEX IF NOT EXISTS idx_user_skills_skill_id ON public.user_skills(skill_id);

-- ============================================================
-- 2. unused_index: удалить неиспользуемые индексы
--    (PostgreSQL stats show zero usage)
-- ============================================================

DROP INDEX IF EXISTS public.idx_jobs_search;
DROP INDEX IF EXISTS public.idx_profiles_search;
DROP INDEX IF EXISTS public.idx_jobs_status;
DROP INDEX IF EXISTS public.idx_jobs_current_workers;
DROP INDEX IF EXISTS public.idx_jobs_status_and_workers;
DROP INDEX IF EXISTS public.idx_notifications_read;
DROP INDEX IF EXISTS public.idx_notifications_created;
DROP INDEX IF EXISTS public.idx_hires_pair;
DROP INDEX IF EXISTS public.idx_hires_date;
