from django.core.management.base import BaseCommand

from datasets.services.parsers.product_match_loader import (
    sync_product_matches_from_classification,
)


class Command(BaseCommand):
    help = (
        "Синхронизирует product match по активной "
        "классификации товаров"
    )

    def handle(self, *args, **options):
        result = (
            sync_product_matches_from_classification()
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Product match synchronized: "
                f"expected={result['active_pairs_expected']}, "
                f"created={result['created_auto']}, "
                f"reactivated={result['reactivated_auto']}, "
                f"inactivated={result['inactivated']}"
            )
        )
