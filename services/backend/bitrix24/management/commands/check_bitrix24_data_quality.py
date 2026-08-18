import json

from django.core.management.base import BaseCommand, CommandError

from bitrix24.services.data_quality import get_bitrix24_data_quality


class Command(BaseCommand):
    help = "Check referential integrity, status mapping and freshness of Bitrix24 data."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        result = get_bitrix24_data_quality()
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        if options["strict"] and result["status"] != "ok":
            raise CommandError("Bitrix24 data-quality checks failed.")
