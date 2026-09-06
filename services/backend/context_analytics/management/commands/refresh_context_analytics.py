from calendar import monthrange
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from context_analytics.models import ContextBackfillCheckpoint, ContextRefreshRun
from context_analytics.services.client import DirectClient
from context_analytics.services.clickhouse import (
    context_warehouse_max_date,
    create_staged_tables,
    discard_staged_tables,
    ensure_tables,
    publish_staged_tables,
    staged_tables_exist,
)
from context_analytics.services.refresh import (
    DEFAULT_INCREMENTAL_DAYS,
    finish,
    heartbeat,
    start_run,
)
from context_analytics.services.warehouse import refresh_warehouse
from seo_analytics.models import SeoGoal
from lead_generation.clickhouse import rebuild_mart_safely


class Command(BaseCommand):
    help = "Первично загружает доступные данные с 2024 года, затем догружает от MAX(date) с перекрытием."

    def add_arguments(self, parser):
        parser.add_argument("--trigger", default="system", choices=("manual", "scheduled", "system"))
        parser.add_argument("--user-id", type=int, default=0)
        parser.add_argument("--days", type=int, default=DEFAULT_INCREMENTAL_DAYS)

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(pk=options["user_id"]).first() if options["user_id"] else None
        run = start_run(options["trigger"], user)
        checkpoint = None
        stats = {}
        try:
            cache.delete_pattern("context:metrika:v1:*")
            today = timezone.localdate()
            date_to = today - timedelta(days=1)
            max_loaded_date = context_warehouse_max_date()
            backfill_completed = ContextRefreshRun.objects.filter(
                status="success",
                stats__initial_backfill=True,
            ).exists()
            initial_backfill = max_loaded_date is None or not backfill_completed
            # Direct хранит статистику только за три года до текущего месяца.
            # Начинаем с согласованной даты 2024-01-01, а в будущем не выходим
            # за фактически доступную API границу.
            earliest_available = max(
                date(2024, 1, 1),
                date(today.year - 3, today.month, 1),
            )
            if initial_backfill:
                date_from = earliest_available
            else:
                anchor = min(max_loaded_date, date_to)
                date_from = max(earliest_available, anchor - timedelta(days=max(1, options["days"]) - 1))
            client = DirectClient()
            if initial_backfill:
                configuration = {
                    "goal_ids": list(
                        SeoGoal.objects.filter(is_available=True)
                        .order_by("external_id")
                        .values_list("external_id", flat=True)
                    ),
                }
                checkpoint = ContextBackfillCheckpoint.objects.filter(key="initial").first()
                if checkpoint is None:
                    _ch, target_tables = create_staged_tables()
                    try:
                        checkpoint = ContextBackfillCheckpoint.objects.create(
                            key="initial",
                            date_from=date_from,
                            date_to=date_to,
                            tables=target_tables,
                            configuration=configuration,
                            stats={
                                "campaigns": 0, "performance_rows": 0, "goal_rows": 0,
                                "criteria_rows": 0, "criteria_goal_rows": 0, "visitor_rows": 0,
                                "months": {}, "initial_backfill": True,
                                "source_earliest_date": earliest_available.isoformat(),
                            },
                        )
                    except Exception:
                        discard_staged_tables(target_tables)
                        raise
                if checkpoint.schema_version != 1 or checkpoint.date_from != date_from:
                    raise RuntimeError(
                        "Сохранённый backfill контекстной аналитики несовместим с текущим окном загрузки. "
                        "Требуется проверить checkpoint перед его сбросом."
                    )
                if checkpoint.configuration != configuration:
                    raise RuntimeError(
                        "Во время незавершённого context backfill изменился каталог доступных целей. "
                        "Продолжение остановлено, чтобы не смешивать состав целей в staging."
                    )
                if not staged_tables_exist(checkpoint.tables):
                    publication_is_visible = (
                        max_loaded_date is not None
                        and checkpoint.completed_through is not None
                        and max_loaded_date >= checkpoint.completed_through
                    )
                    if (
                        checkpoint.status == "publishing"
                        and checkpoint.completed_through == checkpoint.date_to
                        and publication_is_visible
                    ):
                        stats = checkpoint.stats
                        stats["publication_recovered"] = True
                        checkpoint.delete()
                        checkpoint = None
                    else:
                        raise RuntimeError(
                            "Checkpoint контекстного backfill найден, но его staging-таблицы отсутствуют. "
                            "Автоматический повтор с начала остановлен, чтобы не потерять прогресс незаметно."
                        )
                if checkpoint is not None:
                    if date_to > checkpoint.date_to:
                        checkpoint.date_to = date_to
                        checkpoint.save(update_fields=("date_to", "date_update"))
                    stats = checkpoint.stats
                    current = (
                        checkpoint.completed_through + timedelta(days=1)
                        if checkpoint.completed_through else checkpoint.date_from
                    )
                    first_chunk = checkpoint.completed_through is None
                    target = (ensure_tables(), checkpoint.tables)
                    while current <= date_to:
                        chunk_to = min(
                            date(current.year, current.month, monthrange(current.year, current.month)[1]),
                            date_to,
                        )
                        chunk = refresh_warehouse(
                            client, current, chunk_to,
                            staged_target=target,
                            sync_campaigns=first_chunk,
                            progress=lambda step: heartbeat(run, {
                                **stats,
                                "current_step": f"initial_backfill:{step}",
                                "current_period": current.strftime("%Y-%m"),
                            }),
                        )
                        stats["months"][current.strftime("%Y-%m")] = chunk
                        for key in ("campaigns", "performance_rows", "goal_rows", "criteria_rows", "criteria_goal_rows", "visitor_rows"):
                            stats[key] += int(chunk.get(key) or 0)
                        checkpoint.completed_through = chunk_to
                        checkpoint.stats = stats
                        checkpoint.error = ""
                        checkpoint.save(update_fields=("completed_through", "stats", "error", "date_update"))
                        heartbeat(run, {**stats, "current_step": "initial_backfill", "current_period": current.strftime("%Y-%m")})
                        first_chunk = False
                        current = chunk_to + timedelta(days=1)
                    checkpoint.status = "publishing"
                    checkpoint.save(update_fields=("status", "date_update"))
                    publish_staged_tables(checkpoint.tables)
                    checkpoint.delete()
                    checkpoint = None
            else:
                stats = refresh_warehouse(
                    client,
                    date_from,
                    date_to,
                    progress=lambda step: heartbeat(run, {
                        "initial_backfill": False,
                        "current_step": f"incremental:{step}",
                        "date_from": date_from.isoformat(),
                        "date_to": date_to.isoformat(),
                    }),
                )
                stats["initial_backfill"] = False
            stats.update({"date_from": date_from.isoformat(), "date_to": date_to.isoformat()})
            cache.delete_pattern("context:report:*")
            cache.delete_pattern("context:filter-options:*")
            finish(run, stats)
            rebuild_mart_safely()
        except Exception as exc:
            if checkpoint is not None:
                checkpoint.error = str(exc)[:10000]
                checkpoint.save(update_fields=("error", "date_update"))
            finish(run, stats=stats, error=exc)
            raise
        self.stdout.write(self.style.SUCCESS(f"Context refresh #{run.id} completed."))
