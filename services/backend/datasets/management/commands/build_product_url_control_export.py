import os

from django.conf import settings
from django.core.management.base import BaseCommand

from datasets.services.parsers.product_url_export import (
    build_product_url_control_excel,
)


class Command(BaseCommand):
    help = "Build product URL control Excel export and save it to media/datasets"

    def handle(self, *args, **options):
        output_dir = os.path.join(
            settings.BASE_DIR,
            "media",
            "datasets",
        )

        os.makedirs(output_dir, exist_ok=True)

        latest_filename = "parser_product_url_control_latest.xlsx"

        latest_file_path = os.path.join(
            output_dir,
            latest_filename,
        )

        self.stdout.write("Building product URL control export...")

        output = build_product_url_control_excel()
        content = output.getvalue()

        with open(latest_file_path, "wb") as file_obj:
            file_obj.write(content)

        self.stdout.write(
            self.style.SUCCESS(
                f"Export saved: {latest_file_path}"
            )
        )