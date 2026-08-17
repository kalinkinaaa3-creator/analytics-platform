from django.conf import settings
from django.db import models
from decimal import Decimal

from django.utils import timezone
import uuid




class Dashboard(models.Model):

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
        unique=True,
        db_index=True,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

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

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dashboard_access"
        unique_together = ("user", "dashboard")
        verbose_name = "Dashboard access"
        verbose_name_plural = "Dashboard accesses"

    def __str__(self):
        return f"{self.user} → {self.dashboard}"


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
