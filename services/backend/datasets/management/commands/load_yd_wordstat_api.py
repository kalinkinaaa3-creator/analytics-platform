from django.core.management.base import BaseCommand

from analytics.services.yd_wordstat_api_pipeline import run_yd_wordstat_api_pipeline


class Command(BaseCommand):
    help = "Load YD Wordstat from API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["all", "device", "region"],
            default=None,
            help="Optional source. If omitted, full load is executed.",
        )

    def handle(self, *args, **options):
        result = run_yd_wordstat_api_pipeline(
            source=options["source"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"YD Wordstat API load finished: {result}"
            )
        )