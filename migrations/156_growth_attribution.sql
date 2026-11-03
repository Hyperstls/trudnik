-- J157: first-touch UTM attribution + daily activity log (cohorts / retention).
-- Only campaign parameters and a daily marker per user are stored: no IP,
-- user-agent or full referrer URL. user_activity backs DAU/WAU/MAU and cohorts.

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS acquisition jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS user_activity (
    user_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    day date NOT NULL,
    PRIMARY KEY (user_id, day)
);

CREATE INDEX IF NOT EXISTS user_activity_day_idx ON user_activity (day);

-- Seed history from existing actions so cohorts/retention are useful immediately.
INSERT INTO user_activity (user_id, day)
SELECT employer_id, created_at::date FROM jobs
ON CONFLICT DO NOTHING;

INSERT INTO user_activity (user_id, day)
SELECT worker_id, created_at::date FROM applications
ON CONFLICT DO NOTHING;

INSERT INTO user_activity (user_id, day)
SELECT sender_id, created_at::date FROM messages
WHERE deleted_at IS NULL
ON CONFLICT DO NOTHING;
