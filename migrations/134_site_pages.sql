-- ============================================================================
-- Migration 134: site_pages — редактируемые статические страницы (terms/privacy)
-- ============================================================================
-- Даёт админу возможность редактировать текст «Условия использования» и
-- «Политика конфиденциальности» через /admin/content/<slug> вместо правки шаблонов.
-- Чтение — публичное (anon/authenticated), запись — только service_role (админ).
-- core.py /terms и /privacy рендерят содержимое из этой таблицы, если оно есть,
-- иначе откатываются на статичный шаблон (terms.html/privacy.html).
-- Идемпотентно.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.site_pages (
    slug        text PRIMARY KEY,
    title       text NOT NULL DEFAULT '',
    content     text NOT NULL DEFAULT '',
    updated_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.site_pages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS site_pages_read ON public.site_pages;
CREATE POLICY site_pages_read ON public.site_pages
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS site_pages_write ON public.site_pages;
CREATE POLICY site_pages_write ON public.site_pages
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMIT;
