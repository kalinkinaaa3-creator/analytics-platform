from django.core.management.base import BaseCommand

from datasets.services.parsers.product_url_export import (
    save_product_url_control_excel,
)


class Command(BaseCommand):
    help = "Build product URL control Excel export and save it to media/datasets"

    def handle(self, *args, **options):
        self.stdout.write("Building product URL control export...")
        latest_file_path = save_product_url_control_excel()

        self.stdout.write(
            self.style.SUCCESS(
                f"Export saved: {latest_file_path}"
            )
        )
