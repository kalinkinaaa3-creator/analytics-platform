import json
from django.core.management.base import BaseCommand

from analytics.services.yd_wordstat_api_pipeline import run_yd_wordstat_api_pipeline


class Command(BaseCommand):
    help = "Load YD Wordstat from API"

    def add_arguments(self, parser):
        parser.add_argument("--plan", action="store_true", help="Read-only request estimate; no API calls or writes")
        parser.add_argument(
            "--source",
            choices=["all", "device", "region"],
            default=None,
            help="Optional source. If omitted, full load is executed.",
        )

    def handle(self, *args, **options):
        if options["plan"]:
            from datasets.services.external_api.yd_wordstat_api_loader import estimate_load
            result = estimate_load(source=options["source"])
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return
        result = run_yd_wordstat_api_pipeline(
            source=options["source"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"YD Wordstat API load finished: {result}"
            )
        )
