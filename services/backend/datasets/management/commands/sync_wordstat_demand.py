import json
from django.core.management.base import BaseCommand
from analytics.services.yd_wordstat_api_pipeline import wordstat_pipeline_lock
from analytics.services.wordstat_demand_mart import sync_wordstat_demand


class Command(BaseCommand):
    help = "Build/publish the demand ClickHouse mart from saved history; no Wordstat API calls"

    def handle(self, *args, **options):
        with wordstat_pipeline_lock():
            result = sync_wordstat_demand()
        self.stdout.write(json.dumps(result, ensure_ascii=False))
