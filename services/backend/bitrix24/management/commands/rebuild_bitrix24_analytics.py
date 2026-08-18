from django.core.management.base import BaseCommand

from bitrix24.services.calculators import (
    rebuild_lead_analytics,
    rebuild_lead_processing,
    rebuild_stage_intervals,
)


class Command(BaseCommand):
    help = "Rebuild Bitrix24 stage intervals, lead processing and lead analytics."

    def add_arguments(self, parser):
        parser.add_argument("--lead-id", action="append", type=int, dest="lead_ids")

    def handle(self, *args, **options):
        lead_ids = options["lead_ids"]
        interval_count, affected_ids = rebuild_stage_intervals(
            entity_type_id=1,
            entity_ids=lead_ids,
        )
        processing_ids = lead_ids if lead_ids is not None else None
        processing_count = rebuild_lead_processing(lead_ids=processing_ids)
        analytics_count = rebuild_lead_analytics(lead_ids=processing_ids)
        self.stdout.write(
            self.style.SUCCESS(
                "Bitrix24 analytics rebuilt: "
                f"intervals={interval_count}, "
                f"interval_leads={len(affected_ids)}, "
                f"processing={processing_count}, "
                f"analytics={analytics_count}."
            )
        )
