BEGIN;
CREATE TABLE IF NOT EXISTS public.user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    jti text NOT NULL UNIQUE,
    created_at timestamptz DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoked_reason text
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON public.user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_jti ON public.user_sessions(jti);
REVOKE ALL ON public.user_sessions FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON public.user_sessions TO authenticated, service_role;
COMMIT;
