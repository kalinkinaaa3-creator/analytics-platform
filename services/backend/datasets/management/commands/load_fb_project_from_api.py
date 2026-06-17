from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from analytics.services.fb_project_api_pipeline import run_fb_project_api_pipeline


class Command(BaseCommand):
    help = "Load FB Project data from external API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            required=False,
            help="Load date in YYYY-MM-DD format. Default: today.",
        )

    def handle(self, *args, **options):
        load_date = None

        if options.get("date"):
            try:
                load_date = datetime.strptime(
                    options["date"],
                    "%Y-%m-%d",
                ).date()
            except ValueError as exc:
                raise CommandError("Invalid --date format. Use YYYY-MM-DD.") from exc

        result = run_fb_project_api_pipeline(load_date=load_date)

        self.stdout.write(
            self.style.SUCCESS(str(result))
        )