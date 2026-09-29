from django.core.management.base import BaseCommand

from sales_calculator.refresh import drain


class Command(BaseCommand):
    help = "Process queued commercial price refreshes under a PostgreSQL advisory lock"

    def add_arguments(self, parser):
        parser.add_argument("--rebuild", action="store_true", help="Queue a rebuild using already loaded sources")

    def handle(self, *args, **options):
        if options.get("rebuild"):
            from sales_calculator.models import SalesCalculatorRefresh
            SalesCalculatorRefresh.objects.get_or_create(pk=1)
            SalesCalculatorRefresh.objects.filter(pk=1).update(requested=True)
        drain()
