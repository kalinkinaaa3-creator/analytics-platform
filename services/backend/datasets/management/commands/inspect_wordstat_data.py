import json
from django.core.management.base import BaseCommand
from analytics.services.wordstat_health import inspect_wordstat


class Command(BaseCommand):
    help = "Read-only Wordstat coverage diagnostics; no API calls, notifications or database writes"

    def add_arguments(self, parser):
        parser.add_argument("--deep", action="store_true", help="Also verify every saved checkpoint interval (many PostgreSQL queries)")

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(inspect_wordstat(deep=options["deep"]), ensure_ascii=False, indent=2))
