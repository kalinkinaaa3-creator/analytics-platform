from django.apps import AppConfig


class DashboardsConfig(AppConfig):
    name = 'dashboards'

    def ready(self):
        from . import department_signals  # noqa: F401
