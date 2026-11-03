-- 154: chat read receipts (1:1 application chats).
--
-- read_at is set when the other participant opens/polls the chat. The sender
-- sees «Прочитано»; no per-user read table needed for a two-party chat.
ALTER TABLE public.messages
    ADD COLUMN IF NOT EXISTS read_at timestamp with time zone;

CREATE INDEX IF NOT EXISTS idx_messages_unread
    ON public.messages (application_id, sender_id)
    WHERE read_at IS NULL;
