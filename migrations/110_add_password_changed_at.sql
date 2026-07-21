BEGIN;
ALTER TABLE public.profiles 
    ADD COLUMN IF NOT EXISTS password_changed_at timestamptz DEFAULT now();
COMMIT;
