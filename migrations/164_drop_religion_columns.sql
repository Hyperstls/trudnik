-- 164: удалить колонки вероисповедания (152-ФЗ ст.10, спецкатегория).
--
-- profiles.religion_id и jobs.preferred_religion объявлены удалёнными в
-- политике (п. 4.2) и уведомлении РКН, но физически оставались в схеме;
-- 075 выдавал anon SELECT на religion_id. Данные пусты (0 non-null в dev;
-- формы/админ поля не используют с J158/R061). FK fk_profiles_religion_id и
-- column-grant 075 уходят вместе с колонкой автоматически.
-- Справочник religions (словарь без ПДн) НЕ удаляется. Идемпотентно.

ALTER TABLE public.profiles DROP COLUMN IF EXISTS religion_id;
ALTER TABLE public.jobs DROP COLUMN IF EXISTS preferred_religion;
