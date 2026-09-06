import json

from django.core.management.base import BaseCommand, CommandError

from datasets.services.external_api.yd_wordstat_regions_v2_diagnostic import (
    build_regions_v2_diagnostic,
)
from datasets.services.external_api.yd_wordstat_search_api_client import (
    YdWordstatSearchApiError,
    fetch_regions_tree,
)


class Command(BaseCommand):
    help = "Inspect the Wordstat Search API v2 region tree without writing data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--folder-id",
            default=None,
            help="Override YD_WORDSTAT_FOLDER_ID for this diagnostic request only.",
        )

    def handle(self, *args, **options):
        try:
            result = build_regions_v2_diagnostic(
                fetch_regions_tree(folder_id=options["folder_id"])
            )
        except YdWordstatSearchApiError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
