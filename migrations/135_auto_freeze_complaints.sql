-- 135_auto_freeze_complaints.sql
-- Phase 3 (Часть B): жалобы на пользователей + авто-заморозка.
-- Идемпотентно. Без ORM (мутации — через SECURITY DEFINER RPC).

-- ════════════ Таблица жалоб ════════════
CREATE TABLE IF NOT EXISTS user_reports (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_id uuid        NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    reported_id uuid        NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    reason      text        NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now(),
    -- одна жалоба от пользователя на одного пользователя (анти-абуз, дедупликация)
    CONSTRAINT uq_user_reports_pair UNIQUE (reporter_id, reported_id)
);
CREATE INDEX IF NOT EXISTS idx_user_reports_reported_time ON user_reports (reported_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_reports_reporter       ON user_reports (reporter_id);

-- RLS: пользователь видит и подаёт только свои жалобы; service_role обходит (beat-задача).
ALTER TABLE user_reports ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_reports_self_select ON user_reports;
DROP POLICY IF EXISTS user_reports_self_insert ON user_reports;
CREATE POLICY user_reports_self_select ON user_reports
    FOR SELECT USING (
        reporter_id = (current_setting('request.jwt.claims', true)::json->>'user_id')::uuid
    );
CREATE POLICY user_reports_self_insert ON user_reports
    FOR INSERT WITH CHECK (
        reporter_id = (current_setting('request.jwt.claims', true)::json->>'user_id')::uuid
    );

-- ════════════ Признак заморозки в profiles ════════════
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS suspended         boolean     NOT NULL DEFAULT false;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS suspended_reason  text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS suspended_at      timestamptz;
CREATE INDEX IF NOT EXISTS idx_profiles_suspended ON profiles (suspended) WHERE suspended = true;

-- public-чтение profiles уже ограничено; suspended — служебное поле, не отдаём в PUBLIC_PROFILE_FIELDS.

-- ════════════ RPC: подать жалобу (reporter — из JWT, не из параметра) ════════════
CREATE OR REPLACE FUNCTION file_report(p_reported uuid, p_reason text DEFAULT '')
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    v_reporter uuid;
    v_inserted int;
BEGIN
    v_reporter := (current_setting('request.jwt.claims', true)::json->>'user_id')::uuid;
    IF v_reporter IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'not_authenticated');
    END IF;
    IF v_reporter = p_reported THEN
        RETURN jsonb_build_object('ok', false, 'error', 'cannot_report_self');
    END IF;
    INSERT INTO user_reports (reporter_id, reported_id, reason)
    VALUES (v_reporter, p_reported, p_reason)
    ON CONFLICT (reporter_id, reported_id) DO NOTHING;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    RETURN jsonb_build_object('ok', true, 'created', v_inserted > 0);
END;
$$;
REVOKE EXECUTE ON FUNCTION file_report(uuid, text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION file_report(uuid, text) TO authenticated, service_role;

-- ════════════ RPC: кандидаты на заморозку (>= порога жалоб за окно, ещё не заморожены) ════════════
CREATE OR REPLACE FUNCTION users_exceeding_reports(p_threshold int DEFAULT 3, p_hours int DEFAULT 24)
RETURNS TABLE(reported_id uuid, report_count bigint)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
    SELECT r.reported_id, count(*)::bigint
    FROM user_reports r
    JOIN profiles p ON p.id = r.reported_id
    WHERE r.created_at >= now() - make_interval(hours => p_hours)
      AND p.suspended = false
    GROUP BY r.reported_id
    HAVING count(*) >= p_threshold;
$$;
REVOKE EXECUTE ON FUNCTION users_exceeding_reports(int, int) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION users_exceeding_reports(int, int) TO service_role;

-- ════════════ RPC: заморозить / разморозить (только service_role) ════════════
CREATE OR REPLACE FUNCTION suspend_user(p_user_id uuid, p_reason text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE profiles
       SET suspended = true, suspended_reason = p_reason, suspended_at = now()
     WHERE id = p_user_id;
    RETURN FOUND;
END;
$$;
REVOKE EXECUTE ON FUNCTION suspend_user(uuid, text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION suspend_user(uuid, text) TO service_role;

CREATE OR REPLACE FUNCTION unsuspend_user(p_user_id uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE profiles
       SET suspended = false, suspended_reason = NULL, suspended_at = NULL
     WHERE id = p_user_id;
    RETURN FOUND;
END;
$$;
REVOKE EXECUTE ON FUNCTION unsuspend_user(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION unsuspend_user(uuid) TO service_role;

-- ════════════ Админ-модерация жалоб (status + review_complaint) ════════════
ALTER TABLE user_reports ADD COLUMN IF NOT EXISTS status       text        NOT NULL DEFAULT 'new';
ALTER TABLE user_reports ADD COLUMN IF NOT EXISTS reviewed_by  uuid        REFERENCES profiles(id) ON DELETE SET NULL;
ALTER TABLE user_reports ADD COLUMN IF NOT EXISTS reviewed_at  timestamptz;
CREATE INDEX IF NOT EXISTS idx_user_reports_status ON user_reports (status);

-- review_complaint: block → заморозить reported + actioned; dismiss → dismissed.
CREATE OR REPLACE FUNCTION review_complaint(p_report_id uuid, p_action text, p_admin_id uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    v_reported uuid;
BEGIN
    SELECT reported_id INTO v_reported FROM user_reports WHERE id = p_report_id;
    IF v_reported IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'not_found');
    END IF;

    IF p_action = 'block' THEN
        UPDATE profiles
           SET suspended = true, suspended_reason = 'admin: complaint review', suspended_at = now()
         WHERE id = v_reported;
        UPDATE user_reports
           SET status = 'actioned', reviewed_by = p_admin_id, reviewed_at = now()
         WHERE id = p_report_id;
    ELSIF p_action = 'dismiss' THEN
        UPDATE user_reports
           SET status = 'dismissed', reviewed_by = p_admin_id, reviewed_at = now()
         WHERE id = p_report_id;
    ELSE
        RETURN jsonb_build_object('ok', false, 'error', 'bad_action');
    END IF;

    RETURN jsonb_build_object('ok', true, 'reported_id', v_reported);
END;
$$;
REVOKE EXECUTE ON FUNCTION review_complaint(uuid, text, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION review_complaint(uuid, text, uuid) TO service_role;
