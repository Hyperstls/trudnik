from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Трудник (БД)"

    def ready(self):
        # В таблице profiles нет колонки last_login; отключаем штатное обновление,
        # иначе django.contrib.auth.update_last_light упадёт при входе в админку.
        from django.contrib.auth.signals import user_logged_in
        from django.contrib.auth.models import update_last_login

        user_logged_in.disconnect(update_last_login)
