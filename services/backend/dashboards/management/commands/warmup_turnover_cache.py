import calendar
import logging
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from dashboards.models import Dashboard
from dashboards.services.dashboard_builder import build_dashboard


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Warm up builder cache for Turnover dashboard"

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

        User = get_user_model()

        user = User.objects.filter(id=1).first()
        if not user:
            self.stderr.write("User id=1 not found")
            return

        dashboard = Dashboard.objects.filter(name="Turnover").first()
        if not dashboard:
            self.stderr.write('Dashboard "Turnover" not found')
            return

        self.stdout.write("=== Start Turnover cache warmup ===")

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
                f"Warmup {period['name']}: "
                f"{filters['date_start']} -> {filters['date_end']}"
            )

            result = build_dashboard(
                dashboard_id=dashboard.id,
                user=user,
                filters=filters,
            )

            widgets = result.get("widgets", [])
            total_rows = None

            if widgets:
                data = widgets[0].get("data", {})
                total_rows = data.get("total_rows")

            self.stdout.write(
                f"OK: {period['name']}, total_rows={total_rows}"
            )

        self.stdout.write("=== Turnover cache warmup completed ===")