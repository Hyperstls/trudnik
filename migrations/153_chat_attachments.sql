-- 153: chat attachments.
--
-- One attachment per message (image or PDF); text messages unchanged.
ALTER TABLE public.messages
    ADD COLUMN IF NOT EXISTS attachment_url text,
    ADD COLUMN IF NOT EXISTS attachment_name text,
    ADD COLUMN IF NOT EXISTS attachment_mime text,
    ADD COLUMN IF NOT EXISTS attachment_size integer;
