-- Fix: mark all open jobs as paid so they become visible again
-- The payment pipeline is not yet implemented, so all jobs should be visible
UPDATE jobs 
SET is_paid = TRUE,
    paid_at = NOW(),
    expires_at = NOW() + INTERVAL '30 days'
WHERE status IN ('open', 'completed') 
  AND (is_paid = FALSE OR is_paid IS NULL);
