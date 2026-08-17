from datetime import datetime

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.utils import timezone

from datasets.models import IPriceSnapshot
from datasets.services.iprice_snapshot_builder import (
    IPriceSnapshotBuildError,
    build_created_iprice_snapshot,
    build_iprice_snapshot,
)


class Command(BaseCommand):
    help = "Build complete iPrice snapshot"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            required=False,
            help=(
                "Calculation date in YYYY-MM-DD format. "
                "Default: today."
            ),
        )

        parser.add_argument(
            "--snapshot-id",
            type=int,
            required=False,
            help=(
                "Build an already created snapshot "
                "with status=building."
            ),
        )

    def handle(self, *args, **options):
        snapshot_id = options.get(
            "snapshot_id"
        )

        date_value = options.get(
            "date"
        )

        if snapshot_id and date_value:
            raise CommandError(
                (
                    "Use either --snapshot-id "
                    "or --date, not both."
                )
            )

        try:
            if snapshot_id:
                snapshot = (
                    IPriceSnapshot.objects
                    .filter(
                        pk=snapshot_id,
                    )
                    .first()
                )

                if snapshot is None:
                    raise CommandError(
                        (
                            "IPriceSnapshot not found: "
                            f"id={snapshot_id}"
                        )
                    )

                self.stdout.write(
                    (
                        "iPrice snapshot build started: "
                        f"id={snapshot.id}, "
                        f"calculation_date="
                        f"{snapshot.calculation_date}"
                    )
                )

                result = (
                    build_created_iprice_snapshot(
                        snapshot=snapshot,
                    )
                )

            else:
                calculation_date = (
                    self._parse_calculation_date(
                        date_value
                    )
                )

                self.stdout.write(
                    (
                        "iPrice snapshot build started: "
                        f"calculation_date="
                        f"{calculation_date}"
                    )
                )

                result = build_iprice_snapshot(
                    calculation_date=(
                        calculation_date
                    ),
                    parameters={
                        "source": (
                            "management_command"
                        ),
                    },
                )

        except IPriceSnapshotBuildError as exc:
            raise CommandError(
                str(exc)
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                (
                    "iPrice snapshot completed: "
                    f"id={result['snapshot_id']}, "
                    f"version="
                    f"{result['display_version']}, "
                    f"products="
                    f"{result['validation']['products_count']}, "
                    f"regions="
                    f"{result['validation']['regions_count']}, "
                    f"errors="
                    f"{result['validation']['error_regions']}"
                )
            )
        )

    @staticmethod
    def _parse_calculation_date(
        date_value,
    ):
        if not date_value:
            return timezone.localdate()

        try:
            return datetime.strptime(
                date_value,
                "%Y-%m-%d",
            ).date()

        except ValueError as exc:
            raise CommandError(
                (
                    "--date must be in "
                    "YYYY-MM-DD format"
                )
            ) from exc