import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from context_analytics.models import ContextExportRun
from context_analytics.services.export import build_workbook
from context_analytics.services.export_jobs import export_directory


class Command(BaseCommand):
    help = "Builds a context analytics export outside a web request."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", required=True)

    def handle(self, *args, **options):
        try:
            run = ContextExportRun.objects.get(pk=options["run_id"], status="running")
        except ContextExportRun.DoesNotExist as exc:
            raise CommandError("Export run was not found or is no longer active.") from exc
        final_path = export_directory() / f"{run.id}.xlsx"
        partial_path = export_directory() / f"{run.id}.part"

        def heartbeat(_rows):
            ContextExportRun.objects.filter(pk=run.pk, status="running").update(heartbeat_at=timezone.now())

        try:
            build_workbook(run.page, run.filters, partial_path, heartbeat)
            run.refresh_from_db(fields=("status",))
            if run.status != "running":
                partial_path.unlink(missing_ok=True)
                return
            os.replace(partial_path, final_path)
            run.status = "success"
            run.file_path = str(final_path)
            run.finished_at = run.heartbeat_at = timezone.now()
            run.save(update_fields=("status", "file_path", "finished_at", "heartbeat_at"))
        except Exception as exc:
            partial_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            run.status = "failed"
            run.error = str(exc)[:10000]
            run.finished_at = run.heartbeat_at = timezone.now()
            run.save(update_fields=("status", "error", "finished_at", "heartbeat_at"))
            raise CommandError(str(exc)) from exc
