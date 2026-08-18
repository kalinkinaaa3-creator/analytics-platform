from django.core.management.base import BaseCommand

from datasets.services.parsers.product_key_selector import (
    get_active_classified_product_keys,
)

from datasets.services.parsers.ps_product_parser import parse_ps_products
from datasets.services.parsers.product_image_sync import (
    sync_parser_source_images,
)


class Command(BaseCommand):
    help = "Parse PS product cards"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--workers", type=int, default=None)
        parser.add_argument("--retry-failed", action="store_true")
        parser.add_argument("--retry-blocked", action="store_true")
        parser.add_argument(
            "--classified-only",
            action="store_true",
            help=(
                "Parse only active PS product_key values "
                "from active product classification"
            ),
        )

    def handle(self, *args, **options):
        product_keys = None

        if options["classified_only"]:
            product_keys = (
                get_active_classified_product_keys(
                    source="ps",
                )
            )

            self.stdout.write(
                (
                    "PS classified product keys selected: "
                    f"{len(product_keys)}"
                )
            )

        result = parse_ps_products(
            limit=options["limit"],
            workers=options["workers"],
            retry_failed=options["retry_failed"],
            blocked_only=options["retry_blocked"],
            product_keys=product_keys,
        )
        image_sync = sync_parser_source_images("ps")

        self.stdout.write(
            self.style.SUCCESS(
                "PS products parsing finished: "
                f"total={result['total']}, "
                f"success={result['success']}, "
                f"failed={result['failed']}, "
                f"not_found={result['not_found']}, "
                f"blocked={result['blocked']}, "
                f"properties={result['properties']}, "
                f"prices={result['prices']}"
            )
        )
        self.stdout.write(f"PS image sync: {image_sync}")
