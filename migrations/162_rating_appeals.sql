-- 162: апелляции на скрытые отзывы (R023).
--
-- Автор отзыва, скрытого модератором, может подать одну апелляцию. Пока
-- апелляция в статусе pending, повторная подача запрещена частичным UNIQUE
-- индексом. Решение модератора фиксируется в resolved_at/resolver_id.

CREATE TABLE IF NOT EXISTS rating_appeals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rating_id uuid NOT NULL REFERENCES ratings(id) ON DELETE CASCADE,
    appellant_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    resolver_id uuid REFERENCES profiles(id) ON DELETE SET NULL,
    resolution_note text
);

CREATE INDEX IF NOT EXISTS rating_appeals_status_idx
    ON rating_appeals (status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS rating_appeals_pending_uniq
    ON rating_appeals (rating_id)
    WHERE status = 'pending';

GRANT SELECT, INSERT, UPDATE, DELETE ON rating_appeals TO trudnik_dj;
