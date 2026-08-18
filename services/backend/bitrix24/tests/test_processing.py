from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from bitrix24.models import (
    BitrixLead,
    BitrixLeadProcessing,
    BitrixStageHistory,
    BitrixStageInterval,
    BitrixSyncState,
)
from bitrix24.services.calculators import (
    rebuild_lead_processing,
    rebuild_stage_intervals,
)
from bitrix24.services.loaders import load_stage_history

from .test_loaders import FakeClient


class StageHistoryLoaderTests(TestCase):
    def test_incremental_history_returns_affected_leads(self):
        watermark = timezone.now() - timedelta(hours=1)
        BitrixSyncState.objects.create(
            entity="stage_history_1",
            status=BitrixSyncState.Status.SUCCESS,
            last_source_updated_at=watermark,
        )
        created_at = timezone.now()
        client = FakeClient(
            pages={
                "crm.stagehistory.list": [
                    [
                        {
                            "ID": "1",
                            "OWNER_ID": "100",
                            "STATUS_ID": "NEW",
                            "CREATED_TIME": created_at.isoformat(),
                        },
                        {
                            "ID": "2",
                            "OWNER_ID": "100",
                            "STATUS_ID": "IN_PROCESS",
                            "CREATED_TIME": (created_at + timedelta(minutes=5)).isoformat(),
                        },
                    ]
                ]
            }
        )

        run, affected = load_stage_history(client)

        self.assertEqual(run.rows_created, 2)
        self.assertEqual(affected, {100})
        self.assertEqual(BitrixStageHistory.objects.count(), 2)
        self.assertEqual(
            client.calls[0][1]["filter"][">=CREATED_TIME"],
            (watermark - timedelta(minutes=10)).isoformat(),
        )


class LeadProcessingTests(TestCase):
    def setUp(self):
        self.started_at = timezone.now() - timedelta(days=2)
        self.calculated_at = self.started_at + timedelta(days=2)
        BitrixLead.objects.create(
            lead_id=100,
            status_id="IN_PROCESS",
            source_created_at=self.started_at,
        )

    def test_repeated_new_events_do_not_finish_initial_processing(self):
        BitrixStageHistory.objects.bulk_create(
            [
                BitrixStageHistory(
                    history_id=1,
                    entity_type_id=1,
                    entity_id=100,
                    stage_id="NEW",
                    created_at=self.started_at,
                ),
                BitrixStageHistory(
                    history_id=2,
                    entity_type_id=1,
                    entity_id=100,
                    stage_id="NEW",
                    created_at=self.started_at + timedelta(hours=1),
                ),
                BitrixStageHistory(
                    history_id=3,
                    entity_type_id=1,
                    entity_id=100,
                    stage_id="IN_PROCESS",
                    created_at=self.started_at + timedelta(days=1),
                ),
            ]
        )

        interval_count, affected = rebuild_stage_intervals(
            calculated_at=self.calculated_at
        )
        processing_count = rebuild_lead_processing(calculated_at=self.calculated_at)

        self.assertEqual(interval_count, 3)
        self.assertEqual(affected, {100})
        self.assertEqual(processing_count, 1)
        self.assertEqual(BitrixStageInterval.objects.filter(is_current=True).count(), 1)
        processing = BitrixLeadProcessing.objects.get(lead_id=100)
        self.assertEqual(
            processing.processing_state,
            BitrixLeadProcessing.ProcessingState.COMPLETED,
        )
        self.assertEqual(processing.first_processing_at, self.started_at + timedelta(days=1))
        self.assertEqual(processing.processing_duration_seconds, 86400)

    def test_lead_without_history_is_explicitly_marked(self):
        rebuild_lead_processing(calculated_at=self.calculated_at)

        processing = BitrixLeadProcessing.objects.get(lead_id=100)
        self.assertEqual(
            processing.processing_state,
            BitrixLeadProcessing.ProcessingState.NO_HISTORY,
        )
        self.assertIsNone(processing.processing_duration_seconds)

    def test_open_new_stage_is_calculated_until_now(self):
        BitrixLead.objects.filter(lead_id=100).update(status_id="NEW")
        BitrixStageHistory.objects.create(
            history_id=1,
            entity_type_id=1,
            entity_id=100,
            stage_id="NEW",
            created_at=self.started_at,
        )

        rebuild_stage_intervals(calculated_at=self.calculated_at)
        rebuild_lead_processing(calculated_at=self.calculated_at)

        processing = BitrixLeadProcessing.objects.get(lead_id=100)
        self.assertEqual(
            processing.processing_state,
            BitrixLeadProcessing.ProcessingState.IN_PROGRESS,
        )
        self.assertEqual(processing.processing_duration_seconds, 172800)
