-- J158: moderation queue for suspicious job posts (anti-spam / anti-fraud).
-- ``review`` jobs stay visible to their owner but disappear from the public
-- catalog until an admin approves them. ``rejected`` jobs remain hidden.

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS moderation_status text NOT NULL DEFAULT 'ok';
ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS moderation_reason text;

CREATE INDEX IF NOT EXISTS jobs_moderation_status_idx ON jobs (moderation_status);

DO $$ BEGIN
    ALTER TABLE jobs ADD CONSTRAINT jobs_moderation_status_check
        CHECK (moderation_status IN ('ok', 'review', 'rejected'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
