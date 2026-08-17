import time

from django.core.management.base import BaseCommand

from datasets.services.parsers.product_key_selector import (
    get_active_classified_product_keys,
)

from datasets.services.parsers.tara_product_parser import parse_tara_products


class Command(BaseCommand):
    help = "Parse Tara product cards through Playwright browser service"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--workers", type=int, default=None)
        parser.add_argument("--retry-failed", action="store_true")

        parser.add_argument(
            "--retry-blocked",
            action="store_true",
            help="After main pass, retry only blocked Tara products",
        )

        parser.add_argument(
            "--retry-blocked-delay",
            type=int,
            default=300,
        )

        parser.add_argument(
            "--retry-blocked-rounds",
            type=int,
            default=1,
        )

        parser.add_argument(
            "--classified-only",
            action="store_true",
            help=(
                "Parse only active Tara product_key values "
                "from active product classification"
            ),
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        workers = options["workers"]
        retry_failed = options["retry_failed"]

        product_keys = None

        if options["classified_only"]:
            product_keys = (
                get_active_classified_product_keys(
                    source="tara",
                )
            )

            self.stdout.write(
                (
                    "Tara classified product keys selected: "
                    f"{len(product_keys)}"
                )
            )

        self.stdout.write(
            (
                "Tara products parsing started: "
                f"limit={limit}, "
                f"workers={workers}, "
                f"retry_failed={retry_failed}, "
                f"classified_only={options['classified_only']}"
            )
        )

        result = parse_tara_products(
            limit=limit,
            workers=workers,
            retry_failed=retry_failed,
            blocked_only=False,
            product_keys=product_keys,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Tara products parsing finished: "
                f"total={result['total']}, "
                f"success={result['success']}, "
                f"failed={result['failed']}, "
                f"not_found={result['not_found']}, "
                f"blocked={result['blocked']}, "
                f"properties={result['properties']}, "
                f"prices={result['prices']}"
            )
        )

        if not options["retry_blocked"]:
            return

        if result.get("blocked", 0) <= 0:
            self.stdout.write(
                "No blocked Tara products to retry"
            )
            return

        delay = options["retry_blocked_delay"]
        rounds = options["retry_blocked_rounds"]

        for round_number in range(1, rounds + 1):
            self.stdout.write(
                (
                    f"Tara blocked retry round "
                    f"{round_number}/{rounds} "
                    f"will start after {delay} seconds"
                )
            )

            time.sleep(delay)

            retry_result = parse_tara_products(
                limit=None,
                workers=workers,
                retry_failed=False,
                blocked_only=True,
                product_keys=product_keys,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    "Tara blocked retry finished: "
                    f"round={round_number}, "
                    f"total={retry_result['total']}, "
                    f"success={retry_result['success']}, "
                    f"failed={retry_result['failed']}, "
                    f"not_found={retry_result['not_found']}, "
                    f"blocked={retry_result['blocked']}, "
                    f"properties={retry_result['properties']}, "
                    f"prices={retry_result['prices']}"
                )
            )

            if retry_result.get("blocked", 0) <= 0:
                break