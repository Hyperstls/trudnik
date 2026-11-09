-- ============================================================================
-- Migration 166: announcements.sort_order — ручной порядок объявлений /info
-- ============================================================================
-- Владелец управляет порядком в админке (/admin/core/announcement/):
-- закреплённые сверху, затем sort_order (меньше — выше), затем новые.
-- Идемпотентно.

ALTER TABLE public.announcements
    ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0;
