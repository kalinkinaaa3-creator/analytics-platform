from unittest.mock import patch

from django.test import TestCase, override_settings
from datasets.models import ParserMasterPipelineRun, TaraRun
from datasets.parser_queue_models import ParserQueueEntry
from datasets.services.parsers import global_queue as queue
from datasets.services.parsers.queue_execution import master, standalone, tara, tara_can_dispatch
from organizations.models import Organization


@override_settings(PARSER_SHARED_QUEUE_ENABLED=True)
class ParserExecutionTests(TestCase):
    def setUp(self):
        self.iplast = Organization.objects.create(code="iplast", name="Iplast", postgres_schema="public")
        self.sm = Organization.objects.create(code="select-market", name="SM", postgres_schema="select_market")

    def occupy_other(self):
        queue.enqueue(organization=self.sm, kind="master", run_id=100)
        return queue.claim_next(executor="other")

    def test_master_waits_without_executing_when_other_organization_active(self):
        active = self.occupy_other()
        run = ParserMasterPipelineRun.objects.create()
        called = []

        @master
        def task(*, run_id):
            called.append(run_id)
            ParserMasterPipelineRun.objects.filter(pk=run_id).update(status="success")
            return {"status": "success"}

        self.assertTrue(task(run_id=run.pk)["waiting_for_capacity"])
        self.assertEqual(called, [])
        queue.finish(active.pk, active.token, success=True)
        self.assertEqual(task(run_id=run.pk)["status"], "success")
        self.assertEqual(called, [run.pk])
        self.assertFalse(ParserQueueEntry.objects.filter(status__in=ParserQueueEntry.OCCUPIED).exists())

    def test_nested_source_uses_master_slot(self):
        run = ParserMasterPipelineRun.objects.create()

        @standalone("base")
        def source():
            return ParserQueueEntry.objects.filter(status="running").count()

        @master
        def task(*, run_id):
            self.assertEqual(source(), 1)
            ParserMasterPipelineRun.objects.filter(pk=run_id).update(status="success")

        task(run_id=run.pk)
        self.assertEqual(ParserQueueEntry.objects.count(), 1)

    def test_remote_child_keeps_master_slot_until_resume(self):
        run = ParserMasterPipelineRun.objects.create()

        @master
        def task(*, run_id):
            if not TaraRun.objects.filter(master_id=run_id).exists():
                TaraRun.objects.create(master_id=run_id, request_key="child", status="queued")
                ParserMasterPipelineRun.objects.filter(pk=run_id).update(status="waiting_tara")
            else:
                ParserMasterPipelineRun.objects.filter(pk=run_id).update(status="success")

        task(run_id=run.pk)
        self.assertEqual(ParserQueueEntry.objects.get().status, "waiting_remote")
        self.assertEqual(task(run_id=run.pk)["status"], "waiting_tara")
        TaraRun.objects.filter(master=run).update(status="success")
        task(run_id=run.pk)
        self.assertEqual(ParserQueueEntry.objects.get().status, "success")

    def test_manual_source_refuses_busy_slot(self):
        self.occupy_other()

        @standalone("ps")
        def source():
            self.fail("Busy parser must not run")

        with self.assertRaises(queue.QueueOwnershipError):
            source()
        self.assertEqual(ParserQueueEntry.objects.filter(status="cancelled").count(), 1)

    def test_unexpected_exit_holds_slot_for_recovery(self):
        run = ParserMasterPipelineRun.objects.create()

        @master
        def task(*, run_id):
            raise RuntimeError("process error")

        with self.assertRaises(RuntimeError):
            task(run_id=run.pk)
        self.assertEqual(ParserQueueEntry.objects.get().status, "recovery_required")

    def test_standalone_tara_parks_and_resumes_same_entry(self):
        run = TaraRun.objects.create(request_key="manual", status="dispatching", lease="first")

        @tara
        def task(run_id, lease):
            TaraRun.objects.filter(pk=run_id).update(status="waiting_session" if lease == "first" else "success")

        task(run.pk, "first")
        entry = ParserQueueEntry.objects.get()
        self.assertEqual(entry.status, "waiting_remote")
        run.status, run.lease = "dispatching", "second"
        run.save()
        task(run.pk, "second")
        entry.refresh_from_db()
        self.assertEqual(entry.status, "success")

    def test_tara_dispatch_is_denied_during_other_work(self):
        self.occupy_other()
        run = TaraRun.objects.create(request_key="manual", status="queued")
        self.assertFalse(tara_can_dispatch(run))

    def test_failed_remote_child_releases_only_after_execution_returns(self):
        parent = ParserMasterPipelineRun.objects.create(status="waiting_tara")
        entry = queue.enqueue(organization=self.iplast, kind="master", run_id=parent.pk)
        owner = queue.claim_next(executor="master")
        queue.wait_for_remote(owner.pk, owner.token, message="Tara")
        run = TaraRun.objects.create(master=parent, request_key="child", status="dispatching", lease="child-lease")

        @tara
        def task(run_id, lease):
            TaraRun.objects.filter(pk=run_id).update(status="failed")
            ParserMasterPipelineRun.objects.filter(pk=parent.pk).update(status="failed")
            self.assertEqual(ParserQueueEntry.objects.get(pk=entry.pk).status, "waiting_remote")

        task(run.pk, run.lease)
        self.assertEqual(ParserQueueEntry.objects.get(pk=entry.pk).status, "failed")

    @override_settings(PARSER_SHARED_QUEUE_ENABLED=False)
    def test_disabled_mode_preserves_legacy_call(self):
        @standalone("base")
        def source():
            return "legacy"
        self.assertEqual(source(), "legacy")
        self.assertFalse(ParserQueueEntry.objects.exists())
