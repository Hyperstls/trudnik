-- 137_messenger_verify.sql
-- Phase 3 (Часть A): верификация через мессенджеры (MAX + Telegram).
-- Deep-link flow: user → bot /start <token> → webhook → verify_via_messenger RPC.

ALTER TABLE profiles ADD COLUMN IF NOT EXISTS verification_provider text DEFAULT 'manual';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS messenger_user_id text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS verified_at timestamptz;

CREATE OR REPLACE FUNCTION verify_via_messenger(p_user_id uuid, p_provider text, p_messenger_uid text DEFAULT NULL)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE profiles
       SET verification_status  = 'approved',
           verification_provider = p_provider,
           messenger_user_id    = p_messenger_uid,
           verified_at          = now()
     WHERE id = p_user_id;
    RETURN FOUND;
END;
$$;
REVOKE EXECUTE ON FUNCTION verify_via_messenger(uuid, text, text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION verify_via_messenger(uuid, text, text) TO service_role;
