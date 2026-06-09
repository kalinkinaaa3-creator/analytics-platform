from django.conf import settings
from django.db import models


class Dashboard(models.Model):

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboards",
        null=True,
        blank=True,
    )

    name = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    

class DashboardWidget(models.Model):

    WIDGET_TYPES = (
        ("table", "Table"),
        ("line_chart", "Line Chart"),
    )

    dashboard = models.ForeignKey(
        Dashboard,
        related_name="widgets",
        on_delete=models.CASCADE
    )

    type = models.CharField(max_length=50, choices=WIDGET_TYPES)

    config = models.JSONField(default=dict)
    """
    Example:
    {
        "x": "id",
        "y": "amount"
    }
    """

    position = models.IntegerField(default=0)