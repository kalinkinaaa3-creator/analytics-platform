from django.core.management.base import BaseCommand

from datasets.services.parsers.ps_links import sync_ps_product_urls


class Command(BaseCommand):
    help = "Load PS categories and product URLs into ParserProductUrl"

    def handle(self, *args, **options):
        result = sync_ps_product_urls()

        self.stdout.write(
            self.style.SUCCESS(
                "PS links sync finished: "
                f"prefixes={result['prefixes']}, "
                f"categories={result['categories']}, "
                f"category_not_found={result['category_not_found']}, "
                f"category_failed={result['category_failed']}, "
                f"product_urls_found={result['product_urls_found']}, "
                f"active_urls={result['active_urls']}, "
                f"created={result['created']}, "
                f"updated={result['updated']}, "
                f"inactivated={result['inactivated']}, "
                f"skipped={result['skipped']}"
            )
        )