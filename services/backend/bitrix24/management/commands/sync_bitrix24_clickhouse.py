from django.core.management.base import BaseCommand

from bitrix24.services.clickhouse import sync_lead_analytics_to_clickhouse
from lead_generation.clickhouse import rebuild_mart_safely


class Command(BaseCommand):
    help = "Atomically publish the Bitrix24 lead analytics mart to ClickHouse."

    def add_arguments(self, parser):
        parser.add_argument("--chunk-size", type=int, default=1000)

    def handle(self, *args, **options):
        chunk_size = options["chunk_size"]
        if chunk_size <= 0 or chunk_size > 10000:
            raise ValueError("--chunk-size must be between 1 and 10000.")
        inserted = sync_lead_analytics_to_clickhouse(chunk_size=chunk_size)
        rebuild_mart_safely()
        self.stdout.write(
            self.style.SUCCESS(
                f"Bitrix24 ClickHouse mart published: rows={inserted}."
            )
        )
