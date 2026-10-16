from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import IntegrityError, transaction, connection, close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from datasets.parser_queue_models import ParserQueueEntry
from datasets.services.parsers.global_queue import (
    QueueOwnershipError, cancel_queued, claim_next, enqueue, finish,
    flag_stalled, heartbeat, queue_status, resume, wait_for_remote,
)
from organizations.models import Organization


class ParserQueueTests(TestCase):
    def setUp(self):
        self.iplast = Organization.objects.create(code="iplast", name="Iplast", postgres_schema="public")
        self.sm = Organization.objects.create(code="select-market", name="SM", postgres_schema="select_market")

    def enqueue(self, organization=None, run_id=1):
        return enqueue(organization=organization or self.iplast, kind="master", run_id=run_id)

    def test_fifo_between_organizations_and_idempotent_request(self):
        first = self.enqueue()
        second = self.enqueue(self.sm)
        self.assertEqual(self.enqueue().pk, first.pk)
        self.assertEqual(ParserQueueEntry.objects.count(), 2)
        active = claim_next(executor="worker-1")
        self.assertEqual(active.pk, first.pk)
        self.assertIsNone(claim_next(executor="worker-2"))
        finish(active.pk, active.token, success=True)
        self.assertEqual(claim_next(executor="worker-2").pk, second.pk)

    def test_remote_wait_reserves_slot_and_resume_fences_old_callback(self):
        self.enqueue()
        self.enqueue(self.sm)
        active = claim_next(executor="worker-1")
        old_token = active.token
        wait_for_remote(active.pk, old_token, message="Waiting for Tara")
        self.assertIsNone(claim_next(executor="worker-2"))
        with self.assertRaises(QueueOwnershipError):
            finish(active.pk, old_token, success=True)
        active = resume(active.pk, old_token, executor="worker-3")
        with self.assertRaises(QueueOwnershipError):
            heartbeat(active.pk, old_token)
        with self.assertRaises(QueueOwnershipError):
            resume(active.pk, old_token, executor="duplicate")
        finish(active.pk, active.token, success=True)
        self.assertIsNotNone(claim_next(executor="worker-2"))

    def test_stalled_owner_does_not_free_capacity(self):
        self.enqueue()
        self.enqueue(self.sm)
        active = claim_next(executor="worker-1")
        ParserQueueEntry.objects.filter(pk=active.pk).update(heartbeat_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(flag_stalled(), 1)
        heartbeat(active.pk, active.token)
        self.assertIsNone(claim_next(executor="worker-2"))
        with self.assertRaises(QueueOwnershipError):
            finish(active.pk, active.token, success=True)

    def test_cancel_only_queued_and_only_own(self):
        first = self.enqueue()
        second = self.enqueue(self.sm)
        with self.assertRaises(ParserQueueEntry.DoesNotExist):
            cancel_queued(second.pk, organization=self.iplast)
        claim_next(executor="worker")
        with self.assertRaises(QueueOwnershipError):
            cancel_queued(first.pk, organization=self.iplast)
        cancel_queued(second.pk, organization=self.sm)
        self.assertEqual(ParserQueueEntry.objects.get(pk=second.pk).status, "cancelled")

    def test_status_does_not_expose_other_organization_or_token(self):
        self.enqueue()
        own = self.enqueue(self.sm, run_id=99)
        claim_next(executor="worker")
        status = queue_status(organization=self.sm)
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["id"], own.pk)
        self.assertTrue(status[0]["waiting_for_capacity"])
        self.assertNotIn("token", status[0])
        self.assertNotIn("executor", status[0])

    def test_database_rejects_two_occupied_slots(self):
        self.enqueue()
        second = self.enqueue(self.sm)
        claim_next(executor="worker")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParserQueueEntry.objects.filter(pk=second.pk).update(status="waiting_remote")

    def test_failed_job_releases_capacity_without_reusing_old_identity(self):
        first = self.enqueue()
        active = claim_next(executor="worker")
        finish(active.pk, active.token, success=False)
        self.assertEqual(self.enqueue().pk, first.pk)
        self.assertIsNone(claim_next(executor="worker"))
        self.enqueue(run_id=2)
        self.assertIsNotNone(claim_next(executor="worker"))


@skipUnless(connection.vendor == "postgresql", "Requires isolated PostgreSQL test database")
class ConcurrentParserQueueTests(TransactionTestCase):
    def test_two_dispatchers_cannot_claim_different_jobs(self):
        first = Organization.objects.create(code="iplast", name="Iplast", postgres_schema="public")
        second = Organization.objects.create(code="select-market", name="SM", postgres_schema="select_market")
        enqueue(organization=first, kind="master", run_id=1)
        enqueue(organization=second, kind="master", run_id=1)
        barrier = Barrier(2)

        def claim(worker):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                entry = claim_next(executor=worker)
                return entry.pk if entry else None
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(claim, ["one", "two"]))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(ParserQueueEntry.objects.filter(status="running").count(), 1)
