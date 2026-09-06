import json
from calendar import monthrange
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from seo_analytics.models import SeoApiRequestLog, SeoBackfillCheckpoint, SeoBrandMask, SeoGoal, SeoRefreshRun
from seo_analytics.services.options import refresh_filter_options
from seo_analytics.services.client import MetrikaClient
from seo_analytics.services.clickhouse import (
    create_seo_staged_tables,
    discard_seo_staged_tables,
    drop_legacy_report_mart,
    publish_seo_staged_tables,
    seo_staged_tables_exist,
    seo_warehouse_max_month,
    traffic_audience_needs_backfill,
)
from seo_analytics.services.goals import sync_goal_catalog
from seo_analytics.services.refresh import fail_run, finish_run, heartbeat_run, start_run
from seo_analytics.services.warehouse import refresh_warehouse


PAGES = (
    "visits",
    "new-visitors",
    "returning-visitors",
    "search-phrases",
    "traffic-change",
    "conversions",
    "unique-conversions",
    "landing-pages",
)


class Command(BaseCommand):
    help = "Refreshes and warms the default SEO analytics reports."

    def add_arguments(self, parser):
        parser.add_argument("--trigger", choices=[value for value, _ in SeoRefreshRun.Trigger.choices], default=SeoRefreshRun.Trigger.SCHEDULED)
        parser.add_argument("--user-id", type=int, default=0)
        parser.add_argument("--page", choices=PAGES, default="")
        parser.add_argument("--filters-json", default="")
        parser.add_argument("--window", choices=("default", "two-months"), default="default")

    def handle(self, *args, **options):
        user = None
        if options["user_id"]:
            user = get_user_model().objects.filter(id=options["user_id"]).first()
        try:
            run = start_run(trigger=options["trigger"], user=user)
        except Exception as exc:
            raise CommandError(str(exc))

        checkpoint = None
        today = timezone.localdate()
        completed_through = today - timedelta(days=1)
        first_current_month = completed_through.replace(day=1)
        try:
            max_loaded_month = seo_warehouse_max_month()
            audience_needs_backfill = traffic_audience_needs_backfill()
        except Exception as exc:
            fail_run(run, exc)
            raise CommandError(str(exc))
        if max_loaded_month is None or audience_needs_backfill:
            refresh_from = date(2022, 1, 1)
        else:
            anchor_month = min(max_loaded_month.replace(day=1), first_current_month)
            refresh_from = (anchor_month - timedelta(days=1)).replace(day=1)
        base_filters = {
            "date_from": refresh_from.isoformat(),
            "date_to": completed_through.isoformat(),
            "device": [], "search_engine": [], "region": [], "robotness": [],
            "phrase_type": [], "product_category": [], "query_group": [],
        }
        if options["filters_json"]:
            try:
                supplied = json.loads(options["filters_json"])
            except (TypeError, ValueError) as exc:
                fail_run(run, exc)
                raise CommandError("Некорректный --filters-json.")
            base_filters.update(supplied)
        filter_sets = [base_filters]
        warehouse_from = date.fromisoformat(base_filters["date_from"])
        warehouse_to = date.fromisoformat(base_filters["date_to"])
        stats = {"pages": {}, "filters": False, "goals": {}, "warehouse": {}}
        try:
            cache.delete_pattern("seo:report:v1:*")
            cache.delete_pattern("seo:report:v2:*")
            cache.delete_pattern("seo:metrika:v1:*")
            cache.delete("seo:filter-options:v1")
            client = MetrikaClient(progress=lambda report_key, _status: heartbeat_run(run, {
                **stats,
                "current_step": f"metrika:{report_key}",
            }))
            drop_legacy_report_mart()
            stats["goals"] = sync_goal_catalog(client)
            configuration = {
                "goal_ids": list(SeoGoal.objects.filter(is_available=True).order_by("external_id").values_list("external_id", flat=True)),
                "brand_masks": list(SeoBrandMask.objects.filter(is_active=True).order_by("mask").values_list("mask", flat=True)),
            }
            checkpoint = SeoBackfillCheckpoint.objects.filter(key="warehouse").first()
            if (
                checkpoint is not None
                and checkpoint.date_from < date(2022, 1, 1)
                and checkpoint.completed_through is None
            ):
                # A previous empty-warehouse refresh could receive ClickHouse's
                # Date epoch as max(month), producing a 1969-12 checkpoint. No
                # month was completed (Metrika rejects that date), so its shadow
                # tables contain no useful refresh progress and are safe to drop.
                if seo_staged_tables_exist(checkpoint.tables):
                    discard_seo_staged_tables(checkpoint.tables)
                checkpoint.delete()
                checkpoint = None
            if checkpoint is None:
                target_tables = create_seo_staged_tables()
                try:
                    checkpoint = SeoBackfillCheckpoint.objects.create(
                        key="warehouse",
                        date_from=warehouse_from,
                        date_to=warehouse_to,
                        tables=target_tables,
                        configuration=configuration,
                        stats={"warehouse": {}},
                    )
                except Exception:
                    discard_seo_staged_tables(target_tables)
                    raise
            if checkpoint.schema_version != 1 or checkpoint.date_from != warehouse_from:
                raise RuntimeError(
                    "Сохранённый SEO checkpoint несовместим с текущим окном загрузки. "
                    "Требуется проверить checkpoint перед его сбросом."
                )
            if checkpoint.configuration != configuration:
                raise RuntimeError(
                    "Во время незавершённой SEO-загрузки изменились цели или бренд-маски. "
                    "Продолжение остановлено, чтобы не смешивать конфигурации в staging."
                )
            if not seo_staged_tables_exist(checkpoint.tables):
                raise RuntimeError(
                    "SEO checkpoint найден, но его staging-таблицы отсутствуют. "
                    "Автоматический повтор с начала остановлен, чтобы не скрыть потерю прогресса."
                )
            if warehouse_to > checkpoint.date_to:
                checkpoint.date_to = warehouse_to
                checkpoint.save(update_fields=("date_to", "date_update"))
            checkpoint_stats = checkpoint.stats or {"warehouse": {}}
            checkpoint_stats.setdefault("warehouse", {})

            if checkpoint.completed_through:
                completed = checkpoint.completed_through
                completed_month_end = completed.replace(day=monthrange(completed.year, completed.month)[1])
                if completed < completed_month_end and warehouse_to > completed:
                    resume_from = completed.replace(day=1)
                else:
                    resume_from = completed + timedelta(days=1)
            else:
                resume_from = checkpoint.date_from

            def record_progress(month, step, month_stats=None):
                nonlocal checkpoint_stats
                progress_stats = {
                    **stats,
                    "warehouse": checkpoint_stats["warehouse"],
                    "current_step": f"warehouse:{step}",
                    "current_period": month.isoformat(),
                }
                if step == "complete":
                    period_end = min(
                        month.replace(day=monthrange(month.year, month.month)[1]),
                        warehouse_to,
                    )
                    checkpoint.completed_through = period_end
                    checkpoint_stats["warehouse"][month.isoformat()] = month_stats
                    checkpoint.stats = checkpoint_stats
                    checkpoint.error = ""
                    checkpoint.save(update_fields=("completed_through", "stats", "error", "date_update"))
                heartbeat_run(run, progress_stats)

            for filters in filter_sets:
                heartbeat_run(run, {**stats, "current_step": "warehouse"})
                if resume_from <= warehouse_to:
                    refresh_warehouse(
                        client,
                        resume_from,
                        warehouse_to,
                        staged_target=checkpoint.tables,
                        progress=record_progress,
                    )
            stats["warehouse"] = checkpoint_stats["warehouse"]
            checkpoint.status = "publishing"
            checkpoint.save(update_fields=("status", "date_update"))
            publish_seo_staged_tables(checkpoint.tables)
            checkpoint.delete()
            checkpoint = None
            refresh_filter_options()
            cache.delete_pattern("seo:report:v3:*")
            cache.delete_pattern("seo:report:v4:*")
            cache.delete_pattern("seo:report:v5:*")
            cache.delete_pattern("seo:report:v6:*")
            cache.delete_pattern("seo:report:v7:*")
            cache.delete_pattern("context:report:*")
            cache.delete_pattern("context:filter-options:*")
            stats["filters"] = True
            stats["pages"] = {page: "success" for page in PAGES}
            retention_cutoff = timezone.now() - timedelta(days=settings.SEO_LOG_RETENTION_DAYS)
            stats["request_logs_deleted"] = SeoApiRequestLog.objects.filter(created_at__lt=retention_cutoff).delete()[0]
            finish_run(run, stats)
        except Exception as exc:
            if checkpoint is not None:
                checkpoint.error = str(exc)[:10000]
                checkpoint.save(update_fields=("error", "date_update"))
            fail_run(run, exc)
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"SEO analytics refresh #{run.id} completed."))
