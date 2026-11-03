-- 155: editable/deletable chat messages.
--
-- Sender can edit or soft-delete own message. Deleted messages keep the row
-- (so the other side sees «Сообщение удалено»), content/attachment are cleared.
ALTER TABLE public.messages
    ADD COLUMN IF NOT EXISTS edited_at timestamp with time zone,
    ADD COLUMN IF NOT EXISTS deleted_at timestamp with time zone;
