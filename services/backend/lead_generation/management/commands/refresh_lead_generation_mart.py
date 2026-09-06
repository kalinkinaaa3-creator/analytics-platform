from django.core.management.base import BaseCommand

from lead_generation.clickhouse import rebuild_mart


class Command(BaseCommand):
    help = "Atomically rebuild the weekly ClickHouse mart for lead generation."

    def handle(self, *args, **options):
        rows = rebuild_mart()
        self.stdout.write(self.style.SUCCESS(f"Lead generation mart published: rows={rows}."))

