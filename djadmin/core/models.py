"""Unmanaged-модели поверх СУЩЕСТВУЮЩЕЙ схемы PostgreSQL «Трудник».

Источник истины схемы — SQL-миграции migrations/NNN_*.sql (rule 04).
Здесь только маппинг: managed=False у всех моделей, ни одной Django-миграции схемы.
Составные PK user_skills/job_skills (без суррогатного id): primary_key назначен на
первый FK — это влияет только на идентичность объектов в ORM; запись идёт raw-SQL
(см. core.admin.users.skills_view).

Рейтинг profiles.rating/total_reviews/ratings_count пересчитывает триггер
recompute_profile_rating() — в коде НЕ пересчитывать.
"""
import uuid
from datetime import timedelta

import bcrypt
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ProfileManager(BaseUserManager):
    """Менеджер пользователя-профиля + RLS-видимость каталогов (см. §1.3 спеки)."""

    use_in_migrations = False

    def public_workers(self):
        """Каталог трудников: RLS + worker_visibility (админы скрыты правилом RLS)."""
        return self.filter(role="worker", worker_visibility=True)

    def public_visible(self):
        """Публично просматриваемые профили: любые worker/employer, админы скрыты RLS."""
        return self.filter(role__in=("worker", "employer"))

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("email обязателен")
        extra.setdefault("role", "worker")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", "admin")
        extra["email_verified"] = True
        extra["suspended"] = False
        return self.create_user(email, password, full_name=extra.pop("full_name", "Админ Трудник"), **extra)


class Profile(AbstractBaseUser):
    """Пользователь = профиль (таблица profiles; отдельной users-таблицы нет).

    Пароли: bcrypt $2b$/$2a$ 12 раундов — совместимы с Flask (app/utils/auth.py),
    pgcrypto crypt() и Django BCryptPasswordHasher.
    """

    class Role(models.TextChoices):
        WORKER = "worker", _("Трудник")
        EMPLOYER = "employer", _("Работодатель")
        ADMIN = "admin", _("Администратор")

    class VerificationStatus(models.TextChoices):
        NONE = "none", _("Не верифицирован")
        PENDING = "pending", _("На проверке")
        APPROVED = "approved", _("Подтверждён")
        REJECTED = "rejected", _("Отклонён")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(_("роль-ориентация"), max_length=20, choices=Role.choices, default=Role.WORKER)
    full_name = models.CharField(_("ФИО"), max_length=300, default="")
    phone = models.CharField(_("телефон"), max_length=40, null=True, blank=True)
    photo_url = models.URLField(_("фото (legacy)"), max_length=1000, null=True, blank=True)
    avatar_url = models.URLField(_("аватар"), max_length=1000, null=True, blank=True)
    age = models.PositiveIntegerField(_("возраст"), null=True, blank=True)
    bio = models.TextField(_("о себе"), null=True, blank=True)
    city = models.CharField(_("город"), max_length=200, null=True, blank=True)
    experience = models.TextField(_("опыт"), null=True, blank=True)
    desired_payment = models.DecimalField(_("желаемая оплата"), max_digits=12, decimal_places=2, null=True, blank=True)
    verification_status = models.CharField(
        _("верификация"), max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.NONE
    )
    verification_doc_url = models.URLField(_("документ верификации"), max_length=1000, null=True, blank=True)
    rating = models.FloatField(_("рейтинг"), default=0, editable=False)
    total_reviews = models.IntegerField(_("всего отзывов"), default=0, editable=False)
    ratings_count = models.IntegerField(_("количество оценок"), default=0, editable=False)
    worker_rating = models.FloatField(_("рейтинг трудника"), default=0, editable=False)
    worker_ratings_count = models.IntegerField(_("оценок как трудника"), default=0, editable=False)
    employer_rating = models.FloatField(_("рейтинг работодателя"), default=0, editable=False)
    employer_ratings_count = models.IntegerField(_("оценок как работодателя"), default=0, editable=False)
    religion = models.ForeignKey(
        "core.Religion", verbose_name=_("вероисповедание"), on_delete=models.SET_NULL,
        null=True, blank=True, db_column="religion_id", related_name="profiles",
    )
    portfolio_link = models.URLField(_("портфолио"), max_length=1000, default="", blank=True)
    inn = models.CharField(_("ИНН"), max_length=12, default="", blank=True)
    is_self_employed = models.BooleanField(_("самозанятый"), default=False)
    email_public = models.EmailField(_("публичный email"), max_length=320, default="", blank=True)
    contact = models.CharField(_("контакт"), max_length=300, null=True, blank=True)
    notification_prefs = models.JSONField(_("настройки уведомлений"), default=dict, blank=True)
    acquisition = models.JSONField(_("источник привлечения"), default=dict, blank=True)
    email = models.EmailField(_("email (логин)"), max_length=320, unique=True, null=True, blank=True)
    # bcrypt $2b$/$2a$; колонка БД — password_hash (формат совместим с Flask/pgcrypto)
    password = models.CharField(max_length=255, db_column="password_hash")
    created_at = models.DateTimeField(_("создан"), auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(_("обновлён"), auto_now=True, editable=False)
    # fail-closed на ORM-пути: create_user создаёт неподтверждённого пользователя.
    # DB-default остаётся TRUE до P113 (миграция в этом пакете не меняется);
    # create_superuser ставит True явно.
    email_verified = models.BooleanField(_("email подтверждён"), default=False)
    consented_at = models.DateTimeField(_("согласие 152-ФЗ"), null=True, blank=True)
    password_changed_at = models.DateTimeField(_("пароль изменён"), null=True, blank=True)
    suspended = models.BooleanField(_("заблокирован"), default=False)
    suspended_reason = models.TextField(_("причина блокировки"), null=True, blank=True)
    suspended_at = models.DateTimeField(_("дата блокировки"), null=True, blank=True)
    verification_provider = models.CharField(_("способ верификации"), max_length=30, default="manual")
    messenger_user_id = models.CharField(_("id в мессенджере"), max_length=200, null=True, blank=True)
    verified_at = models.DateTimeField(_("верифицирован"), null=True, blank=True)
    worker_visibility = models.BooleanField(_("виден в каталоге трудников"), default=True)
    two_factor_enabled = models.BooleanField(_("двухэтапный вход (email-код)"), default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    # В profiles нет last_login — поле убираем (сигнал отключён в CoreConfig.ready).
    last_login = None

    objects = ProfileManager()

    class Meta:
        managed = False
        db_table = "profiles"
        verbose_name = _("профиль")
        verbose_name_plural = _("Профили")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s (%s)" % (self.full_name or "без имени", self.email or self.id)

    # ── Django-мост ────────────────────────────────────────────────────────
    @property
    def is_active(self):
        return not self.suspended

    def set_password(self, raw_password):
        """Сырой bcrypt — БЕЗ префикса Django-хэшера: тот же формат, что Flask
        (app/utils/auth.py) и pgcrypto crypt(). Префикс $2a$ выбран потому, что
        pgcrypto (register_user RPC, login_direct_sql) генерирует и проверяет
        ТОЛЬКО $2a$; python-bcrypt понимает и $2a$, и $2b$ — совместимость полная.
        Дополнительно двигаем password_changed_at (гасим старые JWT, паритет B10)."""
        if raw_password is None:
            self.password = ""
        else:
            self.password = bcrypt.hashpw(
                raw_password.encode("utf-8"), bcrypt.gensalt(rounds=12, prefix=b"2a")
            ).decode("ascii")
        self.password_changed_at = timezone.now()

    def check_password(self, raw_password) -> bool:
        if not self.password or not raw_password:
            return False
        try:
            return bcrypt.checkpw(raw_password.encode("utf-8"), self.password.encode("ascii"))
        except ValueError:
            return False

    @property
    def is_staff(self):
        return self.role == self.Role.ADMIN

    @property
    def is_superuser(self):
        return self.role == self.Role.ADMIN

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else str(self.id)[:8]

    def has_perm(self, perm, obj=None):  # superuser-шорткат, как PermissionsMixin
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser


class Religion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("название"), max_length=200, unique=True)
    sort_order = models.IntegerField(_("порядок"), default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "religions"
        ordering = ("sort_order", "name")
        verbose_name = _("вероисповедание")
        verbose_name_plural = _("Вероисповедания")

    def __str__(self):
        return self.name


class Skill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("название"), max_length=200, unique=True)
    sort_order = models.IntegerField(_("порядок"), default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "skills"
        ordering = ("sort_order", "name")
        verbose_name = _("навык")
        verbose_name_plural = _("Навыки (справочник)")

    def __str__(self):
        return self.name


class UserSkill(models.Model):
    """Составной PK (user_id, skill_id); запись — raw SQL в admin.skills_view."""

    user = models.ForeignKey(Profile, on_delete=models.CASCADE, db_column="user_id", primary_key=True, related_name="user_skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, db_column="skill_id", related_name="user_skills")

    class Meta:
        managed = False
        db_table = "user_skills"
        unique_together = (("user", "skill"),)
        verbose_name = _("навык профиля")
        verbose_name_plural = _("Навыки профилей")

    def __str__(self):
        return "%s → %s" % (self.user_id, self.skill_id)


class JobManager(models.Manager):
    def public(self):
        """RLS-паритет: каталог — только опубликованные и прошедшие модерацию."""
        return self.filter(
            status__in=("open", "completed", "cancelled"),
            moderation_status="ok",
        )


class Job(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Черновик")
        OPEN = "open", _("Открыта")
        ACTIVE = "active", _("Активна")
        IN_PROGRESS = "in_progress", _("В работе")
        COMPLETED = "completed", _("Завершена")
        CANCELLED = "cancelled", _("Отменена")
        PAID = "paid", _("Оплачена")
        EXPIRED = "expired", _("Истекла")

    class ModerationStatus(models.TextChoices):
        OK = "ok", _("Опубликовано")
        REVIEW = "review", _("На проверке")
        REJECTED = "rejected", _("Отклонено")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(
        Profile, verbose_name=_("работодатель"), on_delete=models.CASCADE,
        db_column="employer_id", related_name="jobs",
    )
    organization_name = models.CharField(_("организация"), max_length=500, default="")
    org_description = models.TextField(_("об организации"), default="", blank=True)
    object_description = models.TextField(_("об объекте"), default="", blank=True)
    detailed_description = models.TextField(_("подробное описание"), default="", blank=True)
    work_type = models.CharField(_("тип работ"), max_length=100, default="")
    address = models.CharField(_("адрес"), max_length=500, null=True, blank=True)
    city = models.CharField(_("город"), max_length=255, null=True, blank=True)
    is_remote = models.BooleanField(_("удалённая работа"), default=False)
    lat = models.FloatField(_("широта"), null=True, blank=True)
    lng = models.FloatField(_("долгота"), null=True, blank=True)
    date_time = models.DateTimeField(_("дата/время работ"))
    payment_amount = models.DecimalField(_("оплата"), max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(_("статус"), max_length=20, choices=Status.choices, default=Status.OPEN)
    moderation_status = models.CharField(
        _("модерация"), max_length=20, choices=ModerationStatus.choices,
        default=ModerationStatus.OK,
    )
    moderation_reason = models.TextField(_("причина модерации"), null=True, blank=True)
    max_workers = models.PositiveIntegerField(_("нужно работников"), default=1, null=True, blank=True)
    current_workers = models.PositiveSmallIntegerField(_("принято"), default=0, null=True, blank=True)
    tariff = models.CharField(_("тариф"), max_length=20, default="standard", null=True, blank=True)
    is_paid = models.BooleanField(_("оплачено размещение"), default=False, null=True, blank=True)
    paid_at = models.DateTimeField(_("оплачено в"), null=True, blank=True)
    expires_at = models.DateTimeField(_("истекает"), null=True, blank=True)
    promoted_until = models.DateTimeField(_("промо до"), null=True, blank=True)
    is_promoted = models.BooleanField(_("промо"), default=False, null=True, blank=True)
    preferred_religion = models.TextField(_("предпочтение по вере"), default="не важно", null=True, blank=True)
    photo_urls = ArrayField(models.TextField(), verbose_name=_("фото (legacy)"), default=list, blank=True)
    skills = models.ManyToManyField(Skill, through="core.JobSkill", related_name="jobs", blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    objects = JobManager()

    class Meta:
        managed = False
        db_table = "jobs"
        verbose_name = _("задание")
        verbose_name_plural = _("Задания")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s — %s" % (self.work_type or "без типа", self.organization_name or self.employer_id)


class JobSkill(models.Model):
    """Составной PK (job_id, skill_id); чтение — через Job.skills."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, db_column="job_id", primary_key=True, related_name="job_skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, db_column="skill_id", related_name="+")

    class Meta:
        managed = False
        db_table = "job_skills"
        unique_together = (("job", "skill"),)
        verbose_name = _("навык задания")
        verbose_name_plural = _("Навыки заданий")

    def __str__(self):
        return "%s → %s" % (self.job_id, self.skill_id)


class JobPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, verbose_name=_("задание"), on_delete=models.CASCADE, related_name="photos")
    photo_url = models.URLField(_("фото"), max_length=1000, default="")
    order_num = models.IntegerField(_("порядок"), default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "job_photos"
        ordering = ("order_num", "created_at")
        verbose_name = _("фото задания")
        verbose_name_plural = _("Фото заданий")

    def __str__(self):
        return "%s #%d" % (self.job_id, self.order_num)


class Application(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Ожидает")
        ACCEPTED = "accepted", _("Принят")
        REJECTED = "rejected", _("Отклонён")
        WITHDRAWN = "withdrawn", _("Отозван")
        CANCELLED = "cancelled", _("Отменён")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, verbose_name=_("задание"), on_delete=models.CASCADE, related_name="applications")
    worker = models.ForeignKey(Profile, verbose_name=_("трудник"), on_delete=models.CASCADE, db_column="worker_id", related_name="+")
    status = models.CharField(_("статус"), max_length=20, choices=Status.choices, default=Status.PENDING)
    # Время ответа работодателя (accepted/rejected); ставит триггер из 161.
    responded_at = models.DateTimeField(null=True, blank=True, editable=False)
    worker_completed_at = models.DateTimeField(
        _("трудник отметил выполнение"), null=True, blank=True,
    )
    contact_paid = models.BooleanField(_("контакт оплачен"), default=False)
    contact_payment_id = models.UUIDField(_("платёж контакта"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "applications"
        unique_together = (("job", "worker"),)
        verbose_name = _("отклик")
        verbose_name_plural = _("Отклики")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s [%s]" % (self.worker_id, self.job_id, self.status)

    @property
    def rating_available(self):
        """Rating opens after completion, or 3 days after the planned date.

        The fallback protects workers when an employer never marks the job
        completed, while still keeping ratings tied to an accepted application.
        """
        if self.status != self.Status.ACCEPTED:
            return False
        job = self.job
        if job.status in (Job.Status.CANCELLED, Job.Status.DRAFT):
            return False
        if job.status == Job.Status.COMPLETED:
            return True
        return bool(job.date_time and job.date_time <= timezone.now() - timedelta(days=3))


class Message(models.Model):
    id = models.BigAutoField(primary_key=True)  # IDENTITY BY DEFAULT
    sender = models.ForeignKey(Profile, verbose_name=_("отправитель"), on_delete=models.CASCADE, related_name="+")
    application = models.ForeignKey(Application, verbose_name=_("отклик (чат)"), on_delete=models.CASCADE, null=True, blank=True, related_name="messages")
    content = models.TextField(_("текст"), blank=True)
    attachment_url = models.TextField(_("вложение"), null=True, blank=True)
    attachment_name = models.TextField(_("имя вложения"), null=True, blank=True)
    attachment_mime = models.TextField(_("MIME вложения"), null=True, blank=True)
    attachment_size = models.PositiveIntegerField(_("размер вложения"), null=True, blank=True)
    read_at = models.DateTimeField(_("прочитано"), null=True, blank=True)
    edited_at = models.DateTimeField(_("изменено"), null=True, blank=True)
    deleted_at = models.DateTimeField(_("удалено"), null=True, blank=True)
    client_message_id = models.UUIDField(_("идемпотентность (client)"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "messages"
        verbose_name = _("сообщение чата")
        verbose_name_plural = _("Сообщения чата")
        ordering = ("created_at",)

    def __str__(self):
        return "#%s → %s" % (self.pk, self.application_id)


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, verbose_name=_("получатель"), on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(_("тип"), max_length=50)
    title = models.CharField(_("заголовок"), max_length=500)
    message = models.TextField(_("текст"), null=True, blank=True)
    job = models.ForeignKey(Job, verbose_name=_("задание"), on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    application = models.ForeignKey(Application, verbose_name=_("отклик"), on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(_("прочитано"), default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "notifications"
        verbose_name = _("уведомление")
        verbose_name_plural = _("Уведомления")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s" % (self.type, self.user_id)


class NotificationOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Ожидает")
        SENT = "sent", _("Отправлено")
        FAILED = "failed", _("Ошибка")
        SKIPPED = "skipped", _("Пропущено")

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Profile, verbose_name=_("получатель"), on_delete=models.CASCADE, related_name="+")
    type = models.CharField(_("тип"), max_length=50)
    title = models.CharField(_("заголовок"), max_length=255)
    body = models.TextField(_("текст"), null=True, blank=True)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(_("статус"), max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.IntegerField(_("попыток"), default=0)
    processed_at = models.DateTimeField(_("обработано"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "notification_outbox"
        verbose_name = _("outbox-запись")
        verbose_name_plural = _("Outbox уведомлений")
        ordering = ("-created_at",)

    def __str__(self):
        return "#%s %s → %s" % (self.pk, self.type, self.status)


class Rating(models.Model):
    class ModerationStatus(models.TextChoices):
        OK = "ok", _("Опубликовано")
        REVIEW = "review", _("На проверке")
        HIDDEN = "hidden", _("Скрыто")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rated_user = models.ForeignKey(Profile, verbose_name=_("оцениваемый"), on_delete=models.CASCADE, related_name="ratings_received")
    rater_user = models.ForeignKey(Profile, verbose_name=_("оценивший"), on_delete=models.CASCADE, related_name="+")
    job = models.ForeignKey(Job, verbose_name=_("задание"), on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    rating_type = models.CharField(max_length=20, choices=Profile.Role.choices)
    target_type = models.CharField(max_length=20, choices=Profile.Role.choices)
    rating = models.PositiveSmallIntegerField(_("оценка"))  # CHECK 1..5 в БД
    comment = models.TextField(_("комментарий"), null=True, blank=True)
    criteria = models.JSONField(_("критерии"), default=dict, blank=True)
    tags = models.JSONField(_("теги"), default=list, blank=True)
    published_at = models.DateTimeField(_("опубликовано"), null=True, blank=True, editable=False)
    reply = models.TextField(_("ответ"), null=True, blank=True)
    replied_at = models.DateTimeField(_("ответ в"), null=True, blank=True)
    moderation_status = models.CharField(
        _("модерация"), max_length=20, choices=ModerationStatus.choices,
        default=ModerationStatus.OK,
    )
    moderation_reason = models.TextField(_("причина модерации"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "ratings"
        unique_together = (("rater_user", "job", "rated_user"),)
        verbose_name = _("оценка")
        verbose_name_plural = _("Оценки")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s: %d★ → %s" % (self.rater_user_id, self.rating, self.rated_user_id)

    @property
    def is_published(self):
        return self.published_at is not None and self.moderation_status == self.ModerationStatus.OK

    @property
    def is_editable(self):
        return self.created_at >= timezone.now() - timedelta(days=14)


class RatingReport(models.Model):
    class Status(models.TextChoices):
        NEW = "new", _("Новая")
        REVIEWED = "reviewed", _("Рассмотрена")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rating = models.ForeignKey(Rating, verbose_name=_("оценка"), on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(Profile, verbose_name=_("жалобщик"), on_delete=models.CASCADE, related_name="rating_reports_filed")
    reason = models.TextField(_("причина"), default="", blank=True)
    status = models.CharField(_("статус"), max_length=20, choices=Status.choices, default=Status.NEW)
    reviewed_by = models.ForeignKey(
        Profile, verbose_name=_("разобрал"), on_delete=models.SET_NULL,
        null=True, blank=True, db_column="reviewed_by", related_name="+",
    )
    reviewed_at = models.DateTimeField(_("разобрано в"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "rating_reports"
        unique_together = (("rating", "reporter"),)
        verbose_name = _("жалоба на отзыв")
        verbose_name_plural = _("Жалобы на отзывы")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s [%s]" % (self.reporter_id, self.rating_id, self.status)


class RatingAppeal(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("На рассмотрении")
        APPROVED = "approved", _("Одобрена")
        REJECTED = "rejected", _("Отклонена")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rating = models.ForeignKey(Rating, verbose_name=_("оценка"), on_delete=models.CASCADE, related_name="appeals")
    appellant = models.ForeignKey(Profile, verbose_name=_("апеллянт"), on_delete=models.CASCADE)
    reason = models.TextField(_("причина"))
    status = models.CharField(_("статус"), max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    resolved_at = models.DateTimeField(_("рассмотрено в"), null=True, blank=True)
    resolver = models.ForeignKey(
        Profile, verbose_name=_("рассмотрел"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    resolution_note = models.TextField(_("комментарий решения"), null=True, blank=True)

    class Meta:
        managed = False
        db_table = "rating_appeals"
        verbose_name = _("апелляция на отзыв")
        verbose_name_plural = _("Апелляции на отзывы")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s [%s]" % (self.appellant_id, self.rating_id, self.status)


class Invitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Ожидает")
        ACCEPTED = "accepted", _("Принято")
        REJECTED = "rejected", _("Отклонено")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, verbose_name=_("задание"), on_delete=models.CASCADE, related_name="invitations")
    employer = models.ForeignKey(Profile, verbose_name=_("работодатель"), on_delete=models.CASCADE, related_name="+")
    worker = models.ForeignKey(Profile, verbose_name=_("трудник"), on_delete=models.CASCADE, db_column="worker_id", related_name="invitations_received")
    status = models.CharField(_("статус"), max_length=20, choices=Status.choices, default=Status.PENDING)
    message = models.TextField(_("сообщение"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    responded_at = models.DateTimeField(_("ответ в"), null=True, blank=True)

    class Meta:
        managed = False
        db_table = "invitations"
        unique_together = (("job", "worker"),)
        verbose_name = _("приглашение")
        verbose_name_plural = _("Приглашения")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s [%s]" % (self.job_id, self.worker_id, self.status)


class Favorite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, verbose_name=_("кто"), on_delete=models.CASCADE, related_name="+")
    target = models.ForeignKey(Profile, verbose_name=_("кого"), on_delete=models.CASCADE, related_name="+")
    favorite_type = models.CharField(_("тип"), max_length=20, default="worker")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "favorites"
        unique_together = (("user", "target", "favorite_type"),)
        verbose_name = _("избранное (люди)")
        verbose_name_plural = _("Избранное (люди)")

    def __str__(self):
        return "%s ♥ %s" % (self.user_id, self.target_id)


class JobFavorite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, verbose_name=_("кто"), on_delete=models.CASCADE, related_name="+")
    job = models.ForeignKey(Job, verbose_name=_("задание"), on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "job_favorites"
        unique_together = (("user", "job"),)
        verbose_name = _("избранное (задания)")
        verbose_name_plural = _("Избранное (задания)")

    def __str__(self):
        return "%s ♥ %s" % (self.user_id, self.job_id)


class Blacklist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, verbose_name=_("кто заблокировал"), on_delete=models.CASCADE, related_name="+")
    blocked_user = models.ForeignKey(Profile, verbose_name=_("заблокирован"), on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "blacklists"
        unique_together = (("user", "blocked_user"),)
        verbose_name = _("чёрный список")
        verbose_name_plural = _("Чёрные списки")

    def __str__(self):
        return "%s ⛔ %s" % (self.user_id, self.blocked_user_id)


class UserReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(Profile, verbose_name=_("жалобщик"), on_delete=models.CASCADE, related_name="reports_filed")
    reported = models.ForeignKey(Profile, verbose_name=_("нарушитель"), on_delete=models.CASCADE, related_name="+")
    reason = models.TextField(_("причина"), default="", blank=True)
    status = models.CharField(_("статус"), max_length=20, default="new")
    reviewed_by = models.ForeignKey(
        Profile, verbose_name=_("разобрал"), on_delete=models.SET_NULL,
        null=True, blank=True, db_column="reviewed_by", related_name="+",
    )
    reviewed_at = models.DateTimeField(_("разобрано в"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "user_reports"
        unique_together = (("reporter", "reported"),)
        verbose_name = _("жалоба")
        verbose_name_plural = _("Жалобы")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s на %s [%s]" % (self.reporter_id, self.reported_id, self.status)


class EmployerDetail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(Profile, verbose_name=_("профиль"), on_delete=models.CASCADE, db_column="user_id", related_name="employer_detail")
    name = models.CharField(_("название"), max_length=300, default="")
    description = models.TextField(_("описание"), null=True, blank=True)
    address = models.TextField(_("адрес"), null=True, blank=True)
    city = models.CharField(_("город"), max_length=200, null=True, blank=True)
    lat = models.FloatField(_("широта"), null=True, blank=True)
    lng = models.FloatField(_("долгота"), null=True, blank=True)
    company_name = models.CharField(_("компания"), max_length=255, null=True, blank=True)
    inn = models.CharField(_("ИНН"), max_length=12, null=True, blank=True)
    is_self_employed = models.BooleanField(_("самозанятый"), default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "employer_details"
        verbose_name = _("карточка работодателя")
        verbose_name_plural = _("Карточки работодателей")

    def __str__(self):
        return self.name or str(self.user_id)


class EmployerSubscription(models.Model):
    class Tariff(models.TextChoices):
        BASIC = "basic", _("Базовый")
        PRO = "pro", _("Про")
        BUSINESS = "business", _("Бизнес")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(Profile, verbose_name=_("работодатель"), on_delete=models.CASCADE, related_name="subscriptions")
    tariff = models.CharField(_("тариф"), max_length=20, choices=Tariff.choices, default=Tariff.BASIC)
    jobs_remaining = models.IntegerField(_("размещений осталось"), default=0)
    is_promoted = models.BooleanField(_("промо"), default=False)
    promoted_until = models.DateTimeField(_("промо до"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "employer_subscriptions"
        verbose_name = _("подписка работодателя")
        verbose_name_plural = _("Подписки работодателей")

    def __str__(self):
        return "%s [%s]" % (self.employer_id, self.tariff)


class JobPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, verbose_name=_("задание"), on_delete=models.CASCADE, related_name="+")
    employer = models.ForeignKey(Profile, verbose_name=_("работодатель"), on_delete=models.CASCADE, related_name="+")
    amount = models.PositiveIntegerField(_("сумма, ₽"))
    tariff = models.CharField(_("тариф"), max_length=20, default="standard")
    type = models.CharField(_("тип"), max_length=30, default="publication")
    status = models.CharField(_("статус"), max_length=20, default="pending")
    transaction_id = models.CharField(_("транзакция"), max_length=255, null=True, blank=True)
    paid_at = models.DateTimeField(_("оплачено в"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "job_payments"
        verbose_name = _("платёж за задание")
        verbose_name_plural = _("Платежи за задания")

    def __str__(self):
        return "%s — %d₽ [%s]" % (self.job_id, self.amount, self.status)


class ArchiveContactPayment(models.Model):
    """Архив оплат контактов (до отключения монетизации). Read-only история."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.UUIDField()
    worker_id = models.UUIDField()
    job_id = models.UUIDField()
    application_id = models.UUIDField(null=True, blank=True)
    amount = models.PositiveIntegerField(_("сумма, ₽"), default=290)
    status = models.CharField(_("статус"), max_length=20, default="pending")
    transaction_id = models.CharField(_("транзакция"), max_length=255, default="")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    paid_at = models.DateTimeField(_("оплачено в"), null=True, blank=True)

    class Meta:
        managed = False
        db_table = "_archive_contact_payments"
        verbose_name = _("архив: оплата контакта")
        verbose_name_plural = _("Архив: оплаты контактов")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s — %d₽ [%s]" % (self.id, self.amount, self.status)


class Receipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact_payment_id = models.UUIDField(_("платёж контакта"), null=True, blank=True)
    church_name = models.TextField(_("храм"), default="")
    church_inn = models.TextField(_("ИНН храма"), default="")
    service_description = models.TextField(_("описание услуги"), default="")
    amount = models.PositiveIntegerField(_("сумма, ₽"), default=0)
    status = models.TextField(_("статус"), default="sent")
    receipt_json = models.JSONField(_("квитанция"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    resent_at = models.DateTimeField(_("переотправлено"), null=True, blank=True)

    class Meta:
        managed = False
        db_table = "receipts"
        verbose_name = _("квитанция (храм)")
        verbose_name_plural = _("Квитанции (храмы)")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s — %d₽" % (self.church_name, self.amount)


class SitePage(models.Model):
    slug = models.CharField("slug", max_length=100, primary_key=True)
    title = models.TextField(_("заголовок"), default="")
    content = models.TextField(_("содержимое (HTML)"), default="")
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "site_pages"
        verbose_name = _("контентная страница")
        verbose_name_plural = _("Контентные страницы")

    def __str__(self):
        return self.slug


class Announcement(models.Model):
    """Управляемые объявления информационной страницы (/info, R017)."""

    class Kind(models.TextChoices):
        NEWS = "news", _("Новость")
        EVENT = "event", _("Событие")
        LINK = "link", _("Ссылка")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(_("тип"), max_length=20, choices=Kind.choices, default=Kind.NEWS)
    title = models.CharField(_("заголовок"), max_length=200)
    body = models.TextField(_("текст"), blank=True, default="")
    url = models.URLField(_("ссылка"), max_length=500, blank=True, default="")
    url_label = models.CharField(_("подпись ссылки"), max_length=200, blank=True, default="")
    is_pinned = models.BooleanField(_("закреплено"), default=False)
    is_active = models.BooleanField(_("активно"), default=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "announcements"
        verbose_name = _("объявление")
        verbose_name_plural = _("Объявления")
        ordering = ("-is_pinned", "-created_at")

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Profile, verbose_name=_("кто"), on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    action = models.CharField(_("действие"), max_length=100)
    table_name = models.CharField(_("таблица"), max_length=100, null=True, blank=True)
    record_id = models.UUIDField(_("запись"), null=True, blank=True)
    old_data = models.JSONField(_("до"), default=None, blank=True, null=True)
    new_data = models.JSONField(_("после"), default=None, blank=True, null=True)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "audit_log"
        verbose_name = _("запись аудита")
        verbose_name_plural = _("Аудит действий")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s %s#%s" % (self.action, self.table_name, self.record_id)


class EmailLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    notification = models.ForeignKey(Notification, verbose_name=_("уведомление"), on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    user = models.ForeignKey(Profile, verbose_name=_("получатель"), on_delete=models.CASCADE, related_name="+")
    to_email = models.TextField(_("кому"), null=True, blank=True)
    subject = models.TextField(_("тема"), null=True, blank=True)
    template_name = models.CharField(_("шаблон"), max_length=100, null=True, blank=True)
    status = models.CharField(_("статус"), max_length=20, default="pending")
    attempts = models.IntegerField(_("попыток"), default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(_("отправлено"), null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "email_log"
        verbose_name = _("письмо (лог)")
        verbose_name_plural = _("Лог писем")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s [%s]" % (self.subject, self.to_email, self.status)


class PushSubscription(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Profile, verbose_name=_("пользователь"), on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.TextField("endpoint")
    p256dh = models.TextField("p256dh")
    auth = models.TextField("auth")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "push_subscriptions"
        verbose_name = _("push-подписка")
        verbose_name_plural = _("Push-подписки")
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s…" % (self.user_id, self.endpoint[:40])


class MonetizationSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(_("ключ"), max_length=200, unique=True)
    value = models.TextField(_("значение"), default="")
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "monetization_settings"
        verbose_name = _("параметр монетизации")
        verbose_name_plural = _("Параметры монетизации")

    def __str__(self):
        return self.key


class TariffSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tariff_key = models.CharField(_("ключ тарифа"), max_length=30, unique=True)
    price = models.PositiveIntegerField(_("цена, ₽"))
    duration_days = models.PositiveIntegerField(_("дней"), default=30)
    renewal_price = models.PositiveIntegerField(_("продление, ₽"), null=True, blank=True)
    is_active = models.BooleanField(_("активен"), default=True)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "tariff_settings"
        verbose_name = _("тариф")
        verbose_name_plural = _("Тарифы")

    def __str__(self):
        return self.tariff_key
