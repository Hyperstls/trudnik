-- 160: announcements — управляемые объявления/новости информационной страницы.
--
-- Отдельная таблица (не site_pages): админ ведёт список карточек с типом
-- (новость/событие/ссылка), закреплением и необязательной внешней ссылкой.
-- Публичная страница /info (R017) читает активные записи, админка (R016B)
-- редактирует все. Идемпотентно.

CREATE TABLE IF NOT EXISTS public.announcements (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind        text NOT NULL DEFAULT 'news',
    title       varchar(200) NOT NULL,
    body        text NOT NULL DEFAULT '',
    url         varchar(500),
    url_label   varchar(200),
    is_pinned   boolean NOT NULL DEFAULT false,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT announcements_kind_check CHECK (kind IN ('news', 'event', 'link'))
);

CREATE INDEX IF NOT EXISTS announcements_active_pinned_idx
    ON public.announcements (is_active, is_pinned DESC, created_at DESC);

DROP TRIGGER IF EXISTS trg_announcements_updated_at ON public.announcements;
CREATE TRIGGER trg_announcements_updated_at
    BEFORE UPDATE ON public.announcements
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

GRANT SELECT, INSERT, UPDATE, DELETE ON public.announcements TO trudnik_dj;
