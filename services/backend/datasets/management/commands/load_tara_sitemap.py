from django.core.management.base import BaseCommand

from datasets.services.parsers.tara_sitemap import sync_tara_sitemap_to_product_urls


class Command(BaseCommand):
    help = "Load Tara sitemap and sync parser product URLs"

    def handle(self, *args, **options):
        result = sync_tara_sitemap_to_product_urls()

        self.stdout.write(
            self.style.SUCCESS(
                "Tara sitemap sync finished: "
                f"source_urls={result['source_urls']}, "
                f"prefixes={result['prefixes']}, "
                f"active_urls={result['active_urls']}, "
                f"created={result['created']}, "
                f"updated={result['updated']}, "
                f"inactivated={result['inactivated']}, "
                f"skipped={result['skipped']}"
            )
        )