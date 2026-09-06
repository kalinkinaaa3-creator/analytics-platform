import json
from django.core.management.base import BaseCommand
from analytics.services.yd_wordstat_api_pipeline import wordstat_pipeline_lock, notify_wordstat_updated
from analytics.services.wordstat_demand_mart import sync_wordstat_demand


class Command(BaseCommand):
    help = "Build/publish the demand ClickHouse mart from saved history; no Wordstat API calls"

    def handle(self, *args, **options):
        with wordstat_pipeline_lock():
            result = sync_wordstat_demand()
            from dashboards.cache.invalidation import invalidate_dashboard_by_name
            invalidate_dashboard_by_name("Wordstat")
            notify_wordstat_updated()
        self.stdout.write(json.dumps(result, ensure_ascii=False))
