from django.conf import settings
from django.db import models
from decimal import Decimal

from django.utils import timezone
import uuid
from django.core.exceptions import ValidationError
from organizations.models import legacy_organization_id




class Dashboard(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, default=legacy_organization_id)
    menu_group = models.CharField(max_length=255, blank=True, default="")
    display_name = models.CharField(max_length=255, blank=True, default="")
    menu_icon = models.CharField(max_length=32, blank=True, default="")
    menu_order = models.PositiveIntegerField(default=0)
    show_in_menu = models.BooleanField(default=True)
    component = models.CharField(max_length=32, default="legacy", choices=[("legacy", "Действующий дашборд"), ("sps", "СПС"), ("suc", "СУЦ")])

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboards",
        null=True,
        blank=True,
    )

    name = models.CharField(max_length=255)

    slug = models.SlugField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "slug"), name="dashboard_org_slug")]

    def clean(self):
        super().clean()
        if self.organization_id and self.slug is not None and type(self).objects.filter(
            organization_id=self.organization_id, slug=self.slug,
        ).exclude(pk=self.pk).exists():
            raise ValidationError({"slug": "Этот адрес уже используется в организации."})
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(organization_id=self.organization_id).exists():
            raise ValidationError("Перенос существующего дашборда в другую организацию требует отдельной миграции.")
        if self.component != "legacy" and self.organization.code == "iplast":
            raise ValidationError("Новые компоненты предназначены для отдельного рабочего пространства.")

    def __str__(self):
        return self.name
    

class DashboardWidget(models.Model):

    WIDGET_TYPES = (
        ("table", "Table"),
        ("line_chart", "Line Chart"),
        ("fb_project_gantt", "FB Project Gantt"),
        ("yd_wordstat_table", "YD Wordstat Table"),
        ("fb_purchases_dashboard", "FB Purchases Dashboard"),
        ("fb_turnover_dashboard", "FB Turnover Dashboard"),
        ("fb_accreceiv_dashboard", "FB Accreceiv Dashboard"),
        ("planned_sales_dashboard", "Planned Sales Dashboard"),
        ("revenue_dashboard", "Revenue Dashboard"),
        ("iprice_dashboard", "iPrice Dashboard"),
        ("crm_analytics_dashboard", "CRM Analytics Dashboard"),
        ("seo_analytics_dashboard", "SEO Analytics Dashboard"),
        ("context_analytics_dashboard", "Context Analytics Dashboard"),
        ("lead_generation_dashboard", "Lead Generation Dashboard"),
        ("sales_calculator_dashboard", "Commercial Price Dashboard"),
    )

    dashboard = models.ForeignKey(
        Dashboard,
        related_name="widgets",
        on_delete=models.CASCADE
    )

    type = models.CharField(max_length=50, choices=WIDGET_TYPES)

    config = models.JSONField(default=dict, blank=True)
    """
    Example:
    {
        "x": "id",
        "y": "amount"
    }
    """

    position = models.IntegerField(default=0)





class DashboardAccess(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboard_accesses",
    )
    dashboard = models.ForeignKey(
        "dashboards.Dashboard",
        on_delete=models.CASCADE,
        related_name="accesses",
    )

    can_view = models.BooleanField(default=True)
    can_edit = models.BooleanField(default=False)
    manual_can_view = models.BooleanField(null=True, editable=False)
    manual_can_edit = models.BooleanField(null=True, editable=False)
    from_department_group = models.BooleanField(default=False, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dashboard_access"
        unique_together = ("user", "dashboard")
        verbose_name = "Dashboard access"
        verbose_name_plural = "Dashboard accesses"

    def __str__(self):
        return f"{self.user} → {self.dashboard}"

    def clean(self):
        super().clean()
        from organizations.models import OrganizationMembership
        if self.user_id and self.dashboard_id and not OrganizationMembership.objects.filter(
            user_id=self.user_id, organization_id=self.dashboard.organization_id, is_active=True,
        ).exists():
            raise ValidationError("Сначала добавьте пользователю доступ к организации дашборда.")


class DashboardDepartmentGroup(models.Model):
    name = models.TextField("Name", blank=True)
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, verbose_name="Dashboard")
    departments = models.JSONField("Department name", default=list)
    can_view = models.BooleanField("Can view", default=True)
    can_edit = models.BooleanField("Can edit", default=False)
    is_active = models.BooleanField("Active", default=True)

    class Meta:
        verbose_name = "Group access"
        verbose_name_plural = "Groups accesses"
        ordering = ("name", "pk")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = "; ".join(dict.fromkeys(self.departments))
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"name"}
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not isinstance(self.departments, list) or not self.departments or any(
            not isinstance(value, str) or not value.strip() or len(value) > 255 for value in self.departments
        ):
            raise ValidationError({"departments": "Выберите хотя бы одно подразделение."})
        self.departments = list(dict.fromkeys(self.departments))
        self.name = "; ".join(self.departments)


class DashboardDepartmentExclusion(models.Model):
    """A deleted personal access must not be recreated by department rules."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "dashboard"), name="dashboard_department_exclusion_unique")]


class DashboardPublicAccess(models.Model):
    dashboard = models.ForeignKey(
        "dashboards.Dashboard",
        on_delete=models.CASCADE,
        related_name="public_links",
    )

    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dashboard_public_access"
        verbose_name = "Dashboard public access"
        verbose_name_plural = "Dashboard public accesses"

    def is_valid(self):
        if not self.is_active:
            return False

        if self.expires_at and self.expires_at < timezone.now():
            return False

        return True

    def __str__(self):
        return f"Public link → {self.dashboard}"




class DashboardPublicGroup(models.Model):
    name = models.CharField(max_length=255)

    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dashboard_public_group"
        verbose_name = "Dashboard public group"
        verbose_name_plural = "Dashboard public groups"

    def is_valid(self):
        if not self.is_active:
            return False

        if self.expires_at and self.expires_at < timezone.now():
            return False

        return True

    def __str__(self):
        return self.name


class DashboardPublicGroupItem(models.Model):
    group = models.ForeignKey(
        DashboardPublicGroup,
        on_delete=models.CASCADE,
        related_name="items",
    )

    dashboard = models.ForeignKey(
        "dashboards.Dashboard",
        on_delete=models.CASCADE,
        related_name="public_group_items",
    )

    section = models.CharField(max_length=255, default="Раздел")
    display_name = models.CharField(max_length=255)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = "dashboard_public_group_item"
        verbose_name = "Dashboard public group item"
        verbose_name_plural = "Dashboard public group items"
        ordering = ("section", "position", "id")
        unique_together = ("group", "dashboard")

    def __str__(self):
        return f"{self.group} → {self.display_name}"





class UserLoginLog(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.SET_NULL, null=True, blank=True)
    organization_name = models.CharField(max_length=255, blank=True, default="")
    full_name = models.CharField(max_length=255, blank=True, default="")
    department_name = models.CharField(max_length=255, blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="login_logs",
    )

    username = models.CharField(max_length=255, blank=True, null=True)
    success = models.BooleanField(default=False)

    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_login_log"
        verbose_name = "User login log"
        verbose_name_plural = "User login logs"

    def __str__(self):
        return f"{self.username} success={self.success}"


class DashboardViewLog(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.SET_NULL, null=True, blank=True)
    organization_name = models.CharField(max_length=255, blank=True, default="")
    full_name = models.CharField(max_length=255, blank=True, default="")
    department_name = models.CharField(max_length=255, blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="dashboard_view_logs",
    )

    dashboard = models.ForeignKey(
        "dashboards.Dashboard",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="view_logs",
    )

    public_access = models.ForeignKey(
        DashboardPublicAccess,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="view_logs",
    )

    access_type = models.CharField(
        max_length=50,
        choices=[
            ("auth", "Authenticated"),
            ("public", "Public"),
        ],
        db_index=True,
    )

    filters = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dashboard_view_log"
        verbose_name = "Dashboard view log"
        verbose_name_plural = "Dashboard view logs"

    def __str__(self):
        return f"{self.dashboard} / {self.access_type}"


class IPriceParameterChangeLog(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="iprice_parameter_change_logs",
    )
    snapshot_id = models.BigIntegerField(db_index=True)
    mode = models.CharField(max_length=20)
    filters = models.JSONField(default=dict, blank=True)
    search = models.TextField(blank=True, default="")
    changes = models.JSONField(default=dict)
    affected = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        default=STATUS_PENDING,
        db_index=True,
    )
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "iprice_parameter_change_log"
        ordering = ("-created_at", "-id")
        verbose_name = "Changing iPrice settings"
        verbose_name_plural = "Changing iPrice settings"

    def __str__(self):
        return f"iPrice snapshot {self.snapshot_id}: {self.status}"


class IPricePriceZoneConfig(models.Model):
    below_market_threshold = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        default=Decimal("-0.03"),
        verbose_name="Нижний порог рынка",
    )
    above_market_threshold = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        default=Decimal("0.03"),
        verbose_name="Верхний порог рынка",
    )
    critical_threshold = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        default=Decimal("0.10"),
        verbose_name="Критический порог",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активная конфигурация",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_iprice_price_zone_configs",
        verbose_name="Кем создана",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата создания",
    )

    class Meta:
        db_table = "iprice_price_zone_config"
        ordering = ("-created_at", "-id")
        verbose_name = "iPrice price zone configuration"
        verbose_name_plural = "iPrice price zone configurations"
        constraints = (
            models.UniqueConstraint(
                fields=("is_active",),
                condition=models.Q(is_active=True),
                name="iprice_one_active_price_zone_config",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(below_market_threshold__lt=0)
                    & models.Q(above_market_threshold__gt=0)
                    & models.Q(critical_threshold__gt=0)
                    & models.Q(
                        below_market_threshold__lt=models.F(
                            "above_market_threshold"
                        )
                    )
                    & models.Q(
                        above_market_threshold__lt=models.F(
                            "critical_threshold"
                        )
                    )
                ),
                name="iprice_price_zone_threshold_order",
            ),
        )

    def __str__(self):
        return (
            f"{self.below_market_threshold} / "
            f"{self.above_market_threshold} / "
            f"{self.critical_threshold}"
        )
