-- 090_admin_dashboard_rpc.sql
-- Замена 9 отдельных count-запросов на один RPC-вызов для админ-дашборда.
-- Устраняет N+1 проблему: вместо 9 HTTP-запросов → 1 RPC.

CREATE OR REPLACE FUNCTION get_admin_dashboard_stats()
RETURNS JSON AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'total_users', (SELECT COUNT(*) FROM profiles),
        'workers', (SELECT COUNT(*) FROM profiles WHERE role='worker'),
        'employers', (SELECT COUNT(*) FROM profiles WHERE role='employer'),
        'admins', (SELECT COUNT(*) FROM profiles WHERE role='admin'),
        'total_jobs', (SELECT COUNT(*) FROM jobs),
        'open_jobs', (SELECT COUNT(*) FROM jobs WHERE status='open'),
        'completed_jobs', (SELECT COUNT(*) FROM jobs WHERE status='completed'),
        'cancelled_jobs', (SELECT COUNT(*) FROM jobs WHERE status='cancelled'),
        'pending_verifications', (SELECT COUNT(*) FROM profiles WHERE verification_status='pending')
    ) INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION get_admin_dashboard_stats() TO service_role;
