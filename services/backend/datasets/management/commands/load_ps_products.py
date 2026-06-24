from django.core.management.base import BaseCommand

from datasets.services.parsers.ps_product_parser import parse_ps_products


class Command(BaseCommand):
    help = "Parse PS product cards"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--workers", type=int, default=None)
        parser.add_argument("--retry-failed", action="store_true")
        parser.add_argument("--retry-blocked", action="store_true")

    def handle(self, *args, **options):
        result = parse_ps_products(
            limit=options["limit"],
            workers=options["workers"],
            retry_failed=options["retry_failed"],
            blocked_only=options["retry_blocked"],
        )

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