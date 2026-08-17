from django.core.management.base import BaseCommand, CommandError

from datasets.models import AnalyticsProductProcessingRun
from datasets.services.parsers.analytics_product_processor import (
    process_analytics_products,
)


class Command(BaseCommand):
    help = "Run independent analytics product classification and matching"

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)

    def handle(self, *args, **options):
        run_id = options["run_id"]
        if not AnalyticsProductProcessingRun.objects.filter(pk=run_id).exists():
            raise CommandError(f"AnalyticsProductProcessingRun id={run_id} not found")
        result = process_analytics_products(run_id)
        self.stdout.write(self.style.SUCCESS(
            f"Analytics product processing completed: run_id={run_id}, "
            f"products={sum(result.get('source_products', {}).values())}"
        ))
