-- 161: application responded_at — время ответа работодателя (R021).
--
-- Момент, когда работодатель разрешил отклик (accepted/rejected). В отличие от
-- updated_at его не сдвигают посторонние правки, поэтому по нему можно считать
-- скорость ответа для репутации. Возврат в pending сбрасывает метку. Идемпотентно.

ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS responded_at timestamp with time zone;

CREATE OR REPLACE FUNCTION public.set_application_responded_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'pending' THEN
        NEW.responded_at := NULL;
    ELSIF NEW.status IN ('accepted', 'rejected')
          AND OLD.status IS DISTINCT FROM NEW.status THEN
        NEW.responded_at := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_applications_responded_at ON public.applications;
CREATE TRIGGER trg_applications_responded_at
    BEFORE UPDATE OF status ON public.applications
    FOR EACH ROW
    EXECUTE FUNCTION public.set_application_responded_at();

-- Старые разрешённые отклики: лучшая доступная аппроксимация — updated_at.
UPDATE public.applications
   SET responded_at = updated_at
 WHERE status IN ('accepted', 'rejected')
   AND responded_at IS NULL;
