import calendar
import logging
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from dashboards.models import Dashboard, DashboardAccess
from dashboards.services.dashboard_builder import build_dashboard


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Warm up builder cache for Turnover dashboard for all users and public cache"

    def handle(self, *args, **options):
        now = datetime.now()
        yesterday = now - timedelta(days=1)

        current_year = now.year
        last_year = current_year - 1
        current_month = now.month

        periods = [
            {
                "name": "current_year_to_yesterday",
                "date_start": datetime(current_year, 1, 1).strftime("%Y-%m-%d"),
                "date_end": yesterday.strftime("%Y-%m-%d"),
            },
            {
                "name": "last_year_to_yesterday",
                "date_start": datetime(last_year, 1, 1).strftime("%Y-%m-%d"),
                "date_end": yesterday.strftime("%Y-%m-%d"),
            },
            {
                "name": "current_month_to_yesterday",
                "date_start": datetime(current_year, current_month, 1).strftime("%Y-%m-%d"),
                "date_end": yesterday.strftime("%Y-%m-%d"),
            },
            {
                "name": "current_month_to_month_end",
                "date_start": datetime(current_year, current_month, 1).strftime("%Y-%m-%d"),
                "date_end": datetime(
                    current_year,
                    current_month,
                    calendar.monthrange(current_year, current_month)[1],
                ).strftime("%Y-%m-%d"),
            },
        ]

        dashboard = Dashboard.objects.filter(name="Turnover").first()

        if not dashboard:
            self.stderr.write('Dashboard "Turnover" not found')
            return

        User = get_user_model()

        users = (
            User.objects
            .filter(
                id__in=DashboardAccess.objects.filter(
                    dashboard=dashboard,
                    can_view=True,
                ).values_list("user_id", flat=True)
            )
            .distinct()
        )

        self.stdout.write("=== Start Turnover cache warmup ===")
        self.stdout.write(f"Users to warmup: {users.count()}")

        for period in periods:
            filters = {
                "nomenclature": "",
                "warehouse_group": "",
                "warehouse": "",
                "quantity": "",
                "date_start": period["date_start"],
                "date_end": period["date_end"],
            }

            self.stdout.write(
                f"Warmup period {period['name']}: "
                f"{filters['date_start']} -> {filters['date_end']}"
            )

            public_result = build_dashboard(
                dashboard_id=dashboard.id,
                user=None,
                filters=filters,
            )

            self.stdout.write(
                f"OK public: {period['name']}, total_rows={self._get_total_rows(public_result)}"
            )

            for user in users:
                result = build_dashboard(
                    dashboard_id=dashboard.id,
                    user=user,
                    filters=filters,
                )

                self.stdout.write(
                    f"OK user={user.id}: {period['name']}, total_rows={self._get_total_rows(result)}"
                )

        self.stdout.write("=== Turnover cache warmup completed ===")

    def _get_total_rows(self, result):
        for widget in result.get("widgets", []):
            data = widget.get("data") or {}

            if "total_rows" in data:
                return data.get("total_rows")

        return None