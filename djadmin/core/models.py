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

import bcrypt
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone


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
        WORKER = "worker", "Трудник"
        EMPLOYER = "employer", "Работодатель"
        ADMIN = "admin", "Администратор"

    class VerificationStatus(models.TextChoices):
        NONE = "none", "Не верифицирован"
        PENDING = "pending", "На проверке"
        APPROVED = "approved", "Подтверждён"
        REJECTED = "rejected", "Отклонён"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField("роль-ориентация", max_length=20, choices=Role.choices, default=Role.WORKER)
    full_name = models.CharField("ФИО", max_length=300, default="")
    phone = models.CharField("телефон", max_length=40, null=True, blank=True)
    photo_url = models.URLField("фото (legacy)", max_length=1000, null=True, blank=True)
    avatar_url = models.URLField("аватар", max_length=1000, null=True, blank=True)
    age = models.PositiveIntegerField("возраст", null=True, blank=True)
    bio = models.TextField("о себе", null=True, blank=True)
    city = models.CharField("город", max_length=200, null=True, blank=True)
    experience = models.TextField("опыт", null=True, blank=True)
    desired_payment = models.DecimalField("желаемая оплата", max_digits=12, decimal_places=2, null=True, blank=True)
    verification_status = models.CharField(
        "верификация", max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.NONE
    )
    verification_doc_url = models.URLField("документ верификации", max_length=1000, null=True, blank=True)
    rating = models.FloatField("рейтинг", default=0, editable=False)
    total_reviews = models.IntegerField("всего отзывов", default=0, editable=False)
    ratings_count = models.IntegerField("количество оценок", default=0, editable=False)
    religion = models.ForeignKey(
        "core.Religion", verbose_name="вероисповедание", on_delete=models.SET_NULL,
        null=True, blank=True, db_column="religion_id", related_name="profiles",
    )
    portfolio_link = models.URLField("портфолио", max_length=1000, default="", blank=True)
    inn = models.CharField("ИНН", max_length=12, default="", blank=True)
    is_self_employed = models.BooleanField("самозанятый", default=False)
    email_public = models.EmailField("публичный email", max_length=320, default="", blank=True)
    contact = models.CharField("контакт", max_length=300, null=True, blank=True)
    notification_prefs = models.JSONField("настройки уведомлений", default=dict, blank=True)
    email = models.EmailField("email (логин)", max_length=320, unique=True, null=True, blank=True)
    # bcrypt $2b$/$2a$; колонка БД — password_hash (формат совместим с Flask/pgcrypto)
    password = models.CharField(max_length=255, db_column="password_hash")
    created_at = models.DateTimeField("создан", auto_now_add=True, editable=False)
    updated_at = models.DateTimeField("обновлён", auto_now=True, editable=False)
    email_verified = models.BooleanField("email подтверждён", default=True)
    consented_at = models.DateTimeField("согласие 152-ФЗ", null=True, blank=True)
    password_changed_at = models.DateTimeField("пароль изменён", null=True, blank=True)
    suspended = models.BooleanField("заблокирован", default=False)
    suspended_reason = models.TextField("причина блокировки", null=True, blank=True)
    suspended_at = models.DateTimeField("дата блокировки", null=True, blank=True)
    verification_provider = models.CharField("способ верификации", max_length=30, default="manual")
    messenger_user_id = models.CharField("id в мессенджере", max_length=200, null=True, blank=True)
    verified_at = models.DateTimeField("верифицирован", null=True, blank=True)
    worker_visibility = models.BooleanField("виден в каталоге трудников", default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    # В profiles нет last_login — поле убираем (сигнал отключён в CoreConfig.ready).
    last_login = None

    objects = ProfileManager()

    class Meta:
        managed = False
        db_table = "profiles"
        verbose_name = "профиль"
        verbose_name_plural = "Профили"
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
    name = models.CharField("название", max_length=200, unique=True)
    sort_order = models.IntegerField("порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "religions"
        ordering = ("sort_order", "name")
        verbose_name = "вероисповедание"
        verbose_name_plural = "Вероисповедания"

    def __str__(self):
        return self.name


class Skill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("название", max_length=200, unique=True)
    sort_order = models.IntegerField("порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "skills"
        ordering = ("sort_order", "name")
        verbose_name = "навык"
        verbose_name_plural = "Навыки (справочник)"

    def __str__(self):
        return self.name


class UserSkill(models.Model):
    """Составной PK (user_id, skill_id); запись — raw SQL в admin.skills_view."""

    user = models.ForeignKey(Profile, on_delete=models.CASCADE, db_column="user_id", primary_key=True, related_name="user_skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, db_column="skill_id", related_name="+")

    class Meta:
        managed = False
        db_table = "user_skills"
        unique_together = (("user", "skill"),)
        verbose_name = "навык профиля"
        verbose_name_plural = "Навыки профилей"

    def __str__(self):
        return "%s → %s" % (self.user_id, self.skill_id)


class JobManager(models.Manager):
    def public(self):
        """RLS-паритет: анонимный каталог показывает только open/completed/cancelled."""
        return self.filter(status__in=("open", "completed", "cancelled"))


class Job(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        OPEN = "open", "Открыта"
        ACTIVE = "active", "Активна"
        IN_PROGRESS = "in_progress", "В работе"
        COMPLETED = "completed", "Завершена"
        CANCELLED = "cancelled", "Отменена"
        PAID = "paid", "Оплачена"
        EXPIRED = "expired", "Истекла"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(
        Profile, verbose_name="работодатель", on_delete=models.CASCADE,
        db_column="employer_id", related_name="jobs",
    )
    organization_name = models.CharField("организация", max_length=500, default="")
    org_description = models.TextField("об организации", default="", blank=True)
    object_description = models.TextField("об объекте", default="", blank=True)
    detailed_description = models.TextField("подробное описание", default="", blank=True)
    work_type = models.CharField("тип работ", max_length=100, default="")
    address = models.CharField("адрес", max_length=500, null=True, blank=True)
    city = models.CharField("город", max_length=255, null=True, blank=True)
    lat = models.FloatField("широта", null=True, blank=True)
    lng = models.FloatField("долгота", null=True, blank=True)
    date_time = models.DateTimeField("дата/время работ")
    payment_amount = models.DecimalField("оплата", max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.OPEN)
    max_workers = models.PositiveIntegerField("нужно работников", default=1, null=True, blank=True)
    current_workers = models.PositiveSmallIntegerField("принято", default=0, null=True, blank=True)
    tariff = models.CharField("тариф", max_length=20, default="standard", null=True, blank=True)
    is_paid = models.BooleanField("оплачено размещение", default=False, null=True, blank=True)
    paid_at = models.DateTimeField("оплачено в", null=True, blank=True)
    expires_at = models.DateTimeField("истекает", null=True, blank=True)
    promoted_until = models.DateTimeField("промо до", null=True, blank=True)
    is_promoted = models.BooleanField("промо", default=False, null=True, blank=True)
    preferred_religion = models.TextField("предпочтение по вере", default="не важно", null=True, blank=True)
    photo_urls = ArrayField(models.TextField(), verbose_name="фото (legacy)", default=list, blank=True)
    skills = models.ManyToManyField(Skill, through="core.JobSkill", related_name="jobs", blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    objects = JobManager()

    class Meta:
        managed = False
        db_table = "jobs"
        verbose_name = "задание"
        verbose_name_plural = "Задания"
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
        verbose_name = "навык задания"
        verbose_name_plural = "Навыки заданий"

    def __str__(self):
        return "%s → %s" % (self.job_id, self.skill_id)


class JobPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, verbose_name="задание", on_delete=models.CASCADE, related_name="photos")
    photo_url = models.URLField("фото", max_length=1000, default="")
    order_num = models.IntegerField("порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "job_photos"
        ordering = ("order_num", "created_at")
        verbose_name = "фото задания"
        verbose_name_plural = "Фото заданий"

    def __str__(self):
        return "%s #%d" % (self.job_id, self.order_num)


class Application(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        ACCEPTED = "accepted", "Принят"
        REJECTED = "rejected", "Отклонён"
        WITHDRAWN = "withdrawn", "Отозван"
        CANCELLED = "cancelled", "Отменён"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, verbose_name="задание", on_delete=models.CASCADE, related_name="applications")
    worker = models.ForeignKey(Profile, verbose_name="трудник", on_delete=models.CASCADE, db_column="worker_id", related_name="+")
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    contact_paid = models.BooleanField("контакт оплачен", default=False)
    contact_payment_id = models.UUIDField("платёж контакта", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "applications"
        unique_together = (("job", "worker"),)
        verbose_name = "отклик"
        verbose_name_plural = "Отклики"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s [%s]" % (self.worker_id, self.job_id, self.status)


class Message(models.Model):
    id = models.BigAutoField(primary_key=True)  # IDENTITY BY DEFAULT
    sender = models.ForeignKey(Profile, verbose_name="отправитель", on_delete=models.CASCADE, related_name="+")
    application = models.ForeignKey(Application, verbose_name="отклик (чат)", on_delete=models.CASCADE, null=True, blank=True, related_name="messages")
    content = models.TextField("текст")
    client_message_id = models.UUIDField("идемпотентность (client)", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "messages"
        verbose_name = "сообщение чата"
        verbose_name_plural = "Сообщения чата"
        ordering = ("created_at",)

    def __str__(self):
        return "#%s → %s" % (self.pk, self.application_id)


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, verbose_name="получатель", on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField("тип", max_length=50)
    title = models.CharField("заголовок", max_length=500)
    message = models.TextField("текст", null=True, blank=True)
    job = models.ForeignKey(Job, verbose_name="задание", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    application = models.ForeignKey(Application, verbose_name="отклик", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField("прочитано", default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "notifications"
        verbose_name = "уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s" % (self.type, self.user_id)


class NotificationOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        SENT = "sent", "Отправлено"
        FAILED = "failed", "Ошибка"
        SKIPPED = "skipped", "Пропущено"

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Profile, verbose_name="получатель", on_delete=models.CASCADE, related_name="+")
    type = models.CharField("тип", max_length=50)
    title = models.CharField("заголовок", max_length=255)
    body = models.TextField("текст", null=True, blank=True)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.IntegerField("попыток", default=0)
    processed_at = models.DateTimeField("обработано", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "notification_outbox"
        verbose_name = "outbox-запись"
        verbose_name_plural = "Outbox уведомлений"
        ordering = ("-created_at",)

    def __str__(self):
        return "#%s %s → %s" % (self.pk, self.type, self.status)


class Rating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rated_user = models.ForeignKey(Profile, verbose_name="оцениваемый", on_delete=models.CASCADE, related_name="ratings_received")
    rater_user = models.ForeignKey(Profile, verbose_name="оценивший", on_delete=models.CASCADE, related_name="+")
    job = models.ForeignKey(Job, verbose_name="задание", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    rating_type = models.CharField(max_length=20, choices=Profile.Role.choices)
    target_type = models.CharField(max_length=20, choices=Profile.Role.choices)
    rating = models.PositiveSmallIntegerField("оценка")  # CHECK 1..5 в БД
    comment = models.TextField("комментарий", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "ratings"
        unique_together = (("rater_user", "job"),)
        verbose_name = "оценка"
        verbose_name_plural = "Оценки"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s: %d★ → %s" % (self.rater_user_id, self.rating, self.rated_user_id)


class Invitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        ACCEPTED = "accepted", "Принято"
        REJECTED = "rejected", "Отклонено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, verbose_name="задание", on_delete=models.CASCADE, related_name="invitations")
    employer = models.ForeignKey(Profile, verbose_name="работодатель", on_delete=models.CASCADE, related_name="+")
    worker = models.ForeignKey(Profile, verbose_name="трудник", on_delete=models.CASCADE, db_column="worker_id", related_name="invitations_received")
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    message = models.TextField("сообщение", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    responded_at = models.DateTimeField("ответ в", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "invitations"
        unique_together = (("job", "worker"),)
        verbose_name = "приглашение"
        verbose_name_plural = "Приглашения"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s [%s]" % (self.job_id, self.worker_id, self.status)


class Favorite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, verbose_name="кто", on_delete=models.CASCADE, related_name="+")
    target = models.ForeignKey(Profile, verbose_name="кого", on_delete=models.CASCADE, related_name="+")
    favorite_type = models.CharField("тип", max_length=20, default="worker")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "favorites"
        unique_together = (("user", "target", "favorite_type"),)
        verbose_name = "избранное (люди)"
        verbose_name_plural = "Избранное (люди)"

    def __str__(self):
        return "%s ♥ %s" % (self.user_id, self.target_id)


class JobFavorite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, verbose_name="кто", on_delete=models.CASCADE, related_name="+")
    job = models.ForeignKey(Job, verbose_name="задание", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "job_favorites"
        unique_together = (("user", "job"),)
        verbose_name = "избранное (задания)"
        verbose_name_plural = "Избранное (задания)"

    def __str__(self):
        return "%s ♥ %s" % (self.user_id, self.job_id)


class Blacklist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Profile, verbose_name="кто заблокировал", on_delete=models.CASCADE, related_name="+")
    blocked_user = models.ForeignKey(Profile, verbose_name="заблокирован", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "blacklists"
        unique_together = (("user", "blocked_user"),)
        verbose_name = "чёрный список"
        verbose_name_plural = "Чёрные списки"

    def __str__(self):
        return "%s ⛔ %s" % (self.user_id, self.blocked_user_id)


class UserReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(Profile, verbose_name="жалобщик", on_delete=models.CASCADE, related_name="reports_filed")
    reported = models.ForeignKey(Profile, verbose_name="нарушитель", on_delete=models.CASCADE, related_name="+")
    reason = models.TextField("причина", default="", blank=True)
    status = models.CharField("статус", max_length=20, default="new")
    reviewed_by = models.ForeignKey(
        Profile, verbose_name="разобрал", on_delete=models.SET_NULL,
        null=True, blank=True, db_column="reviewed_by", related_name="+",
    )
    reviewed_at = models.DateTimeField("разобрано в", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "user_reports"
        unique_together = (("reporter", "reported"),)
        verbose_name = "жалоба"
        verbose_name_plural = "Жалобы"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s на %s [%s]" % (self.reporter_id, self.reported_id, self.status)


class EmployerDetail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(Profile, verbose_name="профиль", on_delete=models.CASCADE, db_column="user_id", related_name="employer_detail")
    name = models.CharField("название", max_length=300, default="")
    description = models.TextField("описание", null=True, blank=True)
    address = models.TextField("адрес", null=True, blank=True)
    city = models.CharField("город", max_length=200, null=True, blank=True)
    lat = models.FloatField("широта", null=True, blank=True)
    lng = models.FloatField("долгота", null=True, blank=True)
    company_name = models.CharField("компания", max_length=255, null=True, blank=True)
    inn = models.CharField("ИНН", max_length=12, null=True, blank=True)
    is_self_employed = models.BooleanField("самозанятый", default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "employer_details"
        verbose_name = "карточка работодателя"
        verbose_name_plural = "Карточки работодателей"

    def __str__(self):
        return self.name or str(self.user_id)


class EmployerSubscription(models.Model):
    class Tariff(models.TextChoices):
        BASIC = "basic", "Базовый"
        PRO = "pro", "Про"
        BUSINESS = "business", "Бизнес"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(Profile, verbose_name="работодатель", on_delete=models.CASCADE, related_name="subscriptions")
    tariff = models.CharField("тариф", max_length=20, choices=Tariff.choices, default=Tariff.BASIC)
    jobs_remaining = models.IntegerField("размещений осталось", default=0)
    is_promoted = models.BooleanField("промо", default=False)
    promoted_until = models.DateTimeField("промо до", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "employer_subscriptions"
        verbose_name = "подписка работодателя"
        verbose_name_plural = "Подписки работодателей"

    def __str__(self):
        return "%s [%s]" % (self.employer_id, self.tariff)


class JobPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, verbose_name="задание", on_delete=models.CASCADE, related_name="+")
    employer = models.ForeignKey(Profile, verbose_name="работодатель", on_delete=models.CASCADE, related_name="+")
    amount = models.PositiveIntegerField("сумма, ₽")
    tariff = models.CharField("тариф", max_length=20, default="standard")
    type = models.CharField("тип", max_length=30, default="publication")
    status = models.CharField("статус", max_length=20, default="pending")
    transaction_id = models.CharField("транзакция", max_length=255, null=True, blank=True)
    paid_at = models.DateTimeField("оплачено в", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "job_payments"
        verbose_name = "платёж за задание"
        verbose_name_plural = "Платежи за задания"

    def __str__(self):
        return "%s — %d₽ [%s]" % (self.job_id, self.amount, self.status)


class ArchiveContactPayment(models.Model):
    """Архив оплат контактов (до отключения монетизации). Read-only история."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.UUIDField()
    worker_id = models.UUIDField()
    job_id = models.UUIDField()
    application_id = models.UUIDField(null=True, blank=True)
    amount = models.PositiveIntegerField("сумма, ₽", default=290)
    status = models.CharField("статус", max_length=20, default="pending")
    transaction_id = models.CharField("транзакция", max_length=255, default="")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    paid_at = models.DateTimeField("оплачено в", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "_archive_contact_payments"
        verbose_name = "архив: оплата контакта"
        verbose_name_plural = "Архив: оплаты контактов"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s — %d₽ [%s]" % (self.id, self.amount, self.status)


class Receipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact_payment_id = models.UUIDField("платёж контакта", null=True, blank=True)
    church_name = models.TextField("храм", default="")
    church_inn = models.TextField("ИНН храма", default="")
    service_description = models.TextField("описание услуги", default="")
    amount = models.PositiveIntegerField("сумма, ₽", default=0)
    status = models.TextField("статус", default="sent")
    receipt_json = models.JSONField("квитанция", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    resent_at = models.DateTimeField("переотправлено", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "receipts"
        verbose_name = "квитанция (храм)"
        verbose_name_plural = "Квитанции (храмы)"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s — %d₽" % (self.church_name, self.amount)


class SitePage(models.Model):
    slug = models.CharField("slug", max_length=100, primary_key=True)
    title = models.TextField("заголовок", default="")
    content = models.TextField("содержимое (HTML)", default="")
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "site_pages"
        verbose_name = "контентная страница"
        verbose_name_plural = "Контентные страницы"

    def __str__(self):
        return self.slug


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Profile, verbose_name="кто", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    action = models.CharField("действие", max_length=100)
    table_name = models.CharField("таблица", max_length=100, null=True, blank=True)
    record_id = models.UUIDField("запись", null=True, blank=True)
    old_data = models.JSONField("до", default=None, blank=True, null=True)
    new_data = models.JSONField("после", default=None, blank=True, null=True)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "audit_log"
        verbose_name = "запись аудита"
        verbose_name_plural = "Аудит действий"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s %s#%s" % (self.action, self.table_name, self.record_id)


class EmailLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    notification = models.ForeignKey(Notification, verbose_name="уведомление", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    user = models.ForeignKey(Profile, verbose_name="получатель", on_delete=models.CASCADE, related_name="+")
    to_email = models.TextField("кому", null=True, blank=True)
    subject = models.TextField("тема", null=True, blank=True)
    template_name = models.CharField("шаблон", max_length=100, null=True, blank=True)
    status = models.CharField("статус", max_length=20, default="pending")
    attempts = models.IntegerField("попыток", default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField("отправлено", null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = False
        db_table = "email_log"
        verbose_name = "письмо (лог)"
        verbose_name_plural = "Лог писем"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s [%s]" % (self.subject, self.to_email, self.status)


class PushSubscription(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Profile, verbose_name="пользователь", on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.TextField("endpoint")
    p256dh = models.TextField("p256dh")
    auth = models.TextField("auth")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "push_subscriptions"
        verbose_name = "push-подписка"
        verbose_name_plural = "Push-подписки"
        ordering = ("-created_at",)

    def __str__(self):
        return "%s → %s…" % (self.user_id, self.endpoint[:40])


class MonetizationSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField("ключ", max_length=200, unique=True)
    value = models.TextField("значение", default="")
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "monetization_settings"
        verbose_name = "параметр монетизации"
        verbose_name_plural = "Параметры монетизации"

    def __str__(self):
        return self.key


class TariffSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tariff_key = models.CharField("ключ тарифа", max_length=30, unique=True)
    price = models.PositiveIntegerField("цена, ₽")
    duration_days = models.PositiveIntegerField("дней", default=30)
    renewal_price = models.PositiveIntegerField("продление, ₽", null=True, blank=True)
    is_active = models.BooleanField("активен", default=True)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        managed = False
        db_table = "tariff_settings"
        verbose_name = "тариф"
        verbose_name_plural = "Тарифы"

    def __str__(self):
        return self.tariff_key
