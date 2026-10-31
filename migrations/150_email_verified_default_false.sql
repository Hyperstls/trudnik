-- 150: fail-closed default for profiles.email_verified.
--
-- Reason: 152-ФЗ / auth hardening. New profiles must not be treated as
-- email-verified unless a flow explicitly sets TRUE (register_user RPC sets
-- FALSE; Profile.set_password/verification flows may set TRUE). Existing rows
-- are not modified; only the column default changes.

ALTER TABLE public.profiles
    ALTER COLUMN email_verified SET DEFAULT false;
