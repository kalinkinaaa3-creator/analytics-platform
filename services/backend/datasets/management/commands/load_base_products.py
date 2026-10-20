from django.core.management.base import BaseCommand, CommandError
from datasets.services.iprice_workspace import IPriceWorkspace

from datasets.services.parsers.base_parser import load_base_products
from datasets.services.parsers.product_image_sync import (
    sync_parser_source_images,
    sync_iprice_product_images,
)


class Command(BaseCommand):
    help = "Load base products from YML/PHP export"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--organization", choices=("iplast", "select-market"), default="iplast")

    def handle(self, *args, **options):
        if options["organization"] == "select-market":
            workspace = IPriceWorkspace("select-market")
            result = load_base_products(limit=options["limit"], workspace=workspace)
            image_sync = sync_iprice_product_images(source="base", workspace=workspace)
        else:
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
        if options["organization"] == "select-market" and result["failed"]:
            raise CommandError(f"Select Market base load has {result['failed']} failed offers")
