from django.core.management.base import BaseCommand

from datasets.services.parsers.base_parser import load_base_products
from datasets.services.parsers.product_image_sync import (
    sync_parser_source_images,
)


class Command(BaseCommand):
    help = "Load base products from YML/PHP export"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        result = load_base_products(limit=options["limit"])
        image_sync = sync_parser_source_images("base")

        self.stdout.write(
            self.style.SUCCESS(
                "Base products load finished: "
                f"offers={result['offers']}, "
                f"parsed={result['parsed']}, "
                f"created={result['created']}, "
                f"updated={result['updated']}, "
                f"inactivated={result['inactivated']}, "
                f"success={result['success']}, "
                f"failed={result['failed']}, "
                f"inactive={result['inactive']}, "
                f"skipped={result['skipped']}, "
                f"properties={result['properties']}, "
                f"prices={result['prices']}"
            )
        )
        self.stdout.write(f"Base image sync: {image_sync}")
