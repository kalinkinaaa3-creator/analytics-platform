from django.core.management.base import BaseCommand

from datasets.services.parsers.tt_links import sync_tt_product_urls


class Command(BaseCommand):
    help = "Load TT categories, product URLs and variations into ParserProductUrl"

    def handle(self, *args, **options):
        result = sync_tt_product_urls()

        self.stdout.write(
            self.style.SUCCESS(
                "TT links sync finished: "
                f"prefixes={result['prefixes']}, "
                f"categories={result['categories']}, "
                f"product_urls_found={result['product_urls_found']}, "
                f"variations_found={result['variations_found']}, "
                f"active_urls={result['active_urls']}, "
                f"created={result['created']}, "
                f"updated={result['updated']}, "
                f"inactivated={result['inactivated']}, "
                f"product_not_found={result['product_not_found']}, "
                f"product_failed={result['product_failed']}, "
                f"skipped={result['skipped']}"
            )
        )