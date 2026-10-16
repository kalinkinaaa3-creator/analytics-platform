from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from datasets.models import ParserMasterPipelineRun, TaraRun, TaraFetch
from datasets.parser_queue_models import ParserQueueEntry
from datasets.services.parsers.global_queue import enqueue, claim_next, heartbeat, QueueOwnershipError
from datasets.services.parsers.queue_recovery import inspect_entry, recover_stopped
from organizations.models import Organization


class RecoveryTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(code="iplast", name="Iplast", postgres_schema="public")
        self.master = ParserMasterPipelineRun.objects.create(status="waiting_tara")
        enqueue(organization=organization, kind="master", run_id=self.master.pk)
        self.owner = claim_next(executor="worker")

    def recover(self, snapshot, **kwargs):
        return recover_stopped(self.owner.pk, expected_fingerprint=snapshot["fingerprint"], operator="operator",
            reason="All backend and remote workers stopped", workers_confirmed_stopped=kwargs.get("confirmed", True))

    def test_requires_confirmation_and_fresh_state(self):
        snapshot = inspect_entry(self.owner.pk)
        with self.assertRaises(ValueError):
            self.recover(snapshot, confirmed=False)
        heartbeat(self.owner.pk, self.owner.token)
        with self.assertRaises(QueueOwnershipError):
            self.recover(snapshot)
        self.assertEqual(ParserQueueEntry.objects.get().status, "running")

    def test_recovery_invalidates_remote_callbacks_and_records_operator(self):
        child = TaraRun.objects.create(master=self.master, request_key="child", status="running", lease="old")
        fetch = TaraFetch.objects.create(run=child, run_lease="old", url="https://example.test", status="claimed",
            token="old-token", expires_at=timezone.now() + timedelta(minutes=1))
        recovered = self.recover(inspect_entry(self.owner.pk))
        self.assertEqual(recovered.status, "failed")
        self.assertEqual(recovered.recovery_audit[0]["operator"], "operator")
        self.master.refresh_from_db()
        child.refresh_from_db()
        fetch.refresh_from_db()
        self.assertEqual(self.master.status, "failed")
        self.assertEqual(child.lease, "")
        self.assertEqual(fetch.status, "expired")
        self.assertEqual(fetch.token, "")
        with self.assertRaises(QueueOwnershipError):
            heartbeat(self.owner.pk, self.owner.token)

    def test_inspection_hides_token_and_does_not_mutate(self):
        snapshot = inspect_entry(self.owner.pk)
        self.assertNotIn("token", snapshot)
        self.assertEqual(ParserQueueEntry.objects.get().status, "running")
