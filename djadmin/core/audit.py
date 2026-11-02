"""Аудит действий админки в таблицу audit_log (паритет log_admin_action Flask).

Guard'ы прав (роль/блокировка админов и т.п.) живут в формах админок (clean) —
отклонение показывается инлайн-ошибкой формы, без двойных сообщений.
"""
from uuid import UUID

from .middleware import client_ip
from .models import AuditLog


def _record_uuid(value, data):
    """AuditLog.record_id is UUID; string-pk pages keep the key in JSON."""
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        if isinstance(data, dict):
            data.setdefault("record_id", str(value)[:100])
        return None


def log_admin_action(request, action: str, table_name: str = "", record_id=None,
                     old_data=None, new_data=None) -> None:
    user = getattr(request, "user", None)
    payload = new_data if new_data is not None else old_data
    AuditLog.objects.create(
        user_id=user.id if (user and user.is_authenticated) else None,
        action=action[:100],
        table_name=table_name[:100] if table_name else None,
        record_id=_record_uuid(record_id, payload),
        old_data=old_data,
        new_data=new_data,
        ip_address=client_ip(request),
    )


class AuditAdminMixin:
    """ModelAdmin-примесь: аудит save/delete (идентификация записи; дифф — в конкретных админках)."""

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_admin_action(
            request,
            action=("update" if change else "create") + "_" + obj._meta.model_name,
            table_name=obj._meta.db_table,
            record_id=getattr(obj, "pk", None),
            new_data={"__str__": str(obj)[:300], "changed": list(form.changed_data)},
        )

    def delete_model(self, request, obj):
        log_admin_action(
            request, action="delete_" + obj._meta.model_name,
            table_name=obj._meta.db_table, record_id=getattr(obj, "pk", None),
            old_data={"__str__": str(obj)[:300]},
        )
        super().delete_model(request, obj)
