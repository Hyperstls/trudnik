"""Celery-задача для drain notification_outbox."""
import logging
from datetime import datetime, timezone

from .celery_app import celery_app
from app.utils import postgrest_admin_request
from app.services.notification_service import get_user_prefs

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def drain_notification_outbox(self):
    """Читает pending-записи из outbox, отправляет через notification_service."""
    try:
        resp = postgrest_admin_request('GET',
            'notification_outbox?status=eq.pending&order=created_at.asc&limit=100')
        if not resp.ok:
            logger.error('drain: fetch failed: %s', resp.status_code)
            return {'processed': 0, 'errors': 1}

        items = resp.json() or []
        processed = 0
        failed = 0
        skipped = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        for item in items:
            attempts = (item.get('attempts') or 0) + 1
            postgrest_admin_request('PATCH',
                f'notification_outbox?id=eq.{item["id"]}',
                json={'attempts': attempts})

            if attempts >= 3:
                postgrest_admin_request('PATCH',
                    f'notification_outbox?id=eq.{item["id"]}',
                    json={'status': 'failed', 'processed_at': now_iso})
                failed += 1
                continue

            try:
                prefs = get_user_prefs(item['user_id'])
                if not prefs.get(item['type'], True):
                    status = 'skipped'
                else:
                    from app.services.notification_service import create as notify_create
                    success = notify_create(
                        user_id=item['user_id'],
                        notification_type=item['type'],
                        title=item.get('title', ''),
                        message=item.get('body', ''),
                        data=item.get('data', {})
                    )
                    status = 'sent' if success else 'failed'
                
                postgrest_admin_request('PATCH',
                    f'notification_outbox?id=eq.{item["id"]}',
                    json={'status': status, 'processed_at': now_iso})
                
                if status == 'sent':
                    processed += 1
                elif status == 'skipped':
                    skipped += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error('drain: error processing item %s: %s', item.get('id'), e)
                failed += 1

        logger.info('drain: processed=%d skipped=%d failed=%d', processed, skipped, failed)
        return {'processed': processed, 'skipped': skipped, 'failed': failed}

    except Exception as e:
        logger.exception('drain: unexpected error: %s', e)
        raise self.retry(exc=e, countdown=30)
