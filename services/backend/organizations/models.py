from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


def legacy_organization_id():
    return Organization.objects.only("pk").get(code="iplast").pk


class Organization(models.Model):
    name = models.CharField("Наименование", max_length=255)
    code = models.SlugField("Системный код", unique=True)
    is_active = models.BooleanField("Активна", default=True)
    theme = models.CharField("Оформление", max_length=32, default="iplast", choices=[
        ("iplast", "Ай-Пласт"), ("select-market", "Селект Маркет"),
    ])
    # Explicit namespaces; existing data is never moved or selected via search_path.
    postgres_schema = models.CharField("Схема PostgreSQL", max_length=63, unique=True,
        validators=[RegexValidator(r"^[a-z][a-z0-9_]*$")])
    clickhouse_database = models.CharField("База ClickHouse", max_length=63, blank=True,
        validators=[RegexValidator(r"^[a-z][a-z0-9_]*$")])

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"
        ordering = ("id",)

    def clean(self):
        super().clean()
        if self.code != "iplast" and self.postgres_schema == "public":
            raise ValidationError("Схема public закреплена за Ай-Пласт.")
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and (previous.code != self.code or previous.postgres_schema != self.postgres_schema):
                raise ValidationError("Код и схема существующей организации неизменяемы.")

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization_profile")
    full_name = models.CharField("ФИО", max_length=255, blank=True)
    note = models.TextField("Примечание", blank=True)

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"


class OrganizationMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization_memberships")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="memberships", verbose_name="Организация")
    department = models.CharField("Отдел", max_length=255, blank=True)
    is_active = models.BooleanField("Доступ активен", default=True)
    is_default = models.BooleanField("По умолчанию", default=False)

    class Meta:
        verbose_name = "Доступ к организации"
        verbose_name_plural = "Доступы к организациям"
        constraints = [
            models.UniqueConstraint(fields=("user", "organization"), name="unique_user_organization"),
            models.UniqueConstraint(fields=("user",), condition=models.Q(is_default=True), name="one_default_organization"),
            models.CheckConstraint(condition=models.Q(is_default=False) | models.Q(is_active=True), name="default_membership_active"),
        ]

    def __str__(self):
        return f"{self.user} — {self.organization}"


class OrganizationSwitchLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    username = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255, blank=True)
    previous_organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, related_name="switches_from")
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, related_name="switches_to")
    previous_organization_name = models.CharField(max_length=255)
    organization_name = models.CharField(max_length=255)
    department_name = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Переключение организации"
        verbose_name_plural = "Переключения организаций"
        ordering = ("-created_at",)
