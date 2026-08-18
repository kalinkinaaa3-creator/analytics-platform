from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from bitrix24.models import BitrixSyncRun, BitrixSyncState
from bitrix24.services.sync_state import (
    BitrixSyncAlreadyRunning,
    BitrixSyncStats,
    fail_sync,
    finish_sync,
    get_incremental_from,
    start_sync,
)


class BitrixSyncStateTests(TestCase):
    def test_success_advances_source_watermark(self):
        watermark = timezone.now()
        run = start_sync("leads", BitrixSyncRun.Mode.INCREMENTAL)

        finish_sync(
            run,
            stats=BitrixSyncStats(rows_received=3, rows_created=1, rows_updated=2),
            last_source_updated_at=watermark,
            last_source_id=25,
        )

        state = BitrixSyncState.objects.get(entity="leads")
        self.assertEqual(state.status, BitrixSyncState.Status.SUCCESS)
        self.assertEqual(state.last_source_updated_at, watermark)
        self.assertEqual(state.last_source_id, 25)
        self.assertEqual(state.rows_received, 3)
        self.assertEqual(
            get_incremental_from("leads", timedelta(minutes=10)),
            watermark - timedelta(minutes=10),
        )

    def test_failure_does_not_advance_source_watermark(self):
        previous = timezone.now() - timedelta(days=1)
        BitrixSyncState.objects.create(
            entity="leads",
            status=BitrixSyncState.Status.SUCCESS,
            last_source_updated_at=previous,
        )
        run = start_sync("leads", BitrixSyncRun.Mode.INCREMENTAL)

        fail_sync(run, ValueError("invalid row"))

        state = BitrixSyncState.objects.get(entity="leads")
        self.assertEqual(state.status, BitrixSyncState.Status.FAILED)
        self.assertEqual(state.last_source_updated_at, previous)
        self.assertIn("ValueError", state.error_text)

    def test_second_run_for_same_entity_is_rejected(self):
        start_sync("leads", BitrixSyncRun.Mode.FULL)

        with self.assertRaises(BitrixSyncAlreadyRunning):
            start_sync("leads", BitrixSyncRun.Mode.INCREMENTAL)
