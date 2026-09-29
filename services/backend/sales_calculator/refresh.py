import logging
import os
import subprocess
import sys
from contextvars import ContextVar
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from .models import SalesCalculatorRefresh

logger = logging.getLogger("sales_calculator")
IN_REFRESH = ContextVar("sales_calculator_refresh", default=False)
LOCK_ID = 83100427


def request_refresh(*, sources=False):
    state_payload()
    SalesCalculatorRefresh.objects.get_or_create(pk=1)
    with transaction.atomic():
        state = SalesCalculatorRefresh.objects.select_for_update().get(pk=1)
        if sources and (state.requested or state.status == "running"):
            return False
        state.requested = True
        state.refresh_sources = state.refresh_sources or sources
        if state.status != "running":
            state.status = "queued"
            state.started_at = timezone.now()
        state.save()
    folder = Path(settings.BASE_DIR) / "logs" / "sales_calculator"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with (folder / "refresh.log").open("ab", buffering=0) as output:
            kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            subprocess.Popen([sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), "refresh_sales_calculator"],
                             cwd=settings.BASE_DIR, stdout=output, stderr=subprocess.STDOUT, **kwargs)
    except Exception:
        SalesCalculatorRefresh.objects.filter(pk=1, status="queued").update(status="failed", error="Не удалось запустить обновление")
        raise
    return True


def source_updated(source=None):
    if IN_REFRESH.get():
        return
    try:
        SalesCalculatorRefresh.objects.get_or_create(pk=1)
        if source == "price":
            SalesCalculatorRefresh.objects.filter(pk=1).update(price_updated_at=timezone.now())
        elif source == "stock":
            SalesCalculatorRefresh.objects.filter(pk=1).update(stock_updated_at=timezone.now(), stock_failed_at=None)
        request_refresh()
    except Exception:
        # The original source load must not be reported as failed after committing its data.
        logger.exception("Could not request commercial price rebuild")


def drain():
    from datasets.models import NomenclaturePrice, NomenclatureStock
    from datasets.services.external_api.price_api_loader import load_prices_from_api
    from datasets.services.external_api.stock_api_loader import load_stocks_from_api
    from .warehouse import publish
    SalesCalculatorRefresh.objects.get_or_create(pk=1)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
        if not cursor.fetchone()[0]:
            return
    token = IN_REFRESH.set(True)
    lock_held = True
    try:
        while True:
            with transaction.atomic():
                state = SalesCalculatorRefresh.objects.select_for_update().get(pk=1)
                if not state.requested:
                    # Release under row lock: a simultaneous new request starts a new worker.
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
                    lock_held = False
                    return
                sources = state.refresh_sources
                state.requested = state.refresh_sources = False
                state.status, state.error = "running", ""
                state.started_at, state.finished_at = timezone.now(), None
                state.save()
            logger.info("Commercial price refresh started: refresh_sources=%s", sources)
            day = timezone.localdate()
            updates = {}
            try:
                if sources:
                    load_prices_from_api(start_date=day, end_date=day)
                    updates["price_updated_at"] = timezone.now()
                    SalesCalculatorRefresh.objects.filter(pk=1).update(**updates)
                if not NomenclaturePrice.objects.filter(date=day).exists():
                    raise ValueError("Прайс за сегодня отсутствует. Прежняя витрина сохранена.")
                stock_ok = NomenclatureStock.objects.filter(date=day).exists() and state.stock_failed_at is None
                if sources:
                    try:
                        load_stocks_from_api(start_date=day, end_date=day)
                        updates["stock_updated_at"] = timezone.now()
                        updates["stock_failed_at"] = None
                        stock_ok = True
                    except Exception:
                        logger.exception("Stock refresh failed; publishing with unavailable stock")
                        stock_ok = False
                        updates["stock_failed_at"] = timezone.now()
                count = publish(day, stock_ok)
                logger.info("Commercial price published: date=%s rows=%s stock_available=%s", day, count, stock_ok)
                updates.update(status="success", row_count=count, stock_available=stock_ok,
                               error="" if stock_ok else "Информация по остаткам временно недоступна")
            except Exception:
                logger.exception("Commercial price refresh failed")
                updates.update(status="failed", error="Не удалось обновить коммерческий прайс. Последняя опубликованная витрина сохранена.")
            updates["finished_at"] = timezone.now()
            SalesCalculatorRefresh.objects.filter(pk=1).update(**updates)
    finally:
        IN_REFRESH.reset(token)
        if lock_held:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])


def state_payload():
    state = SalesCalculatorRefresh.objects.filter(pk=1).values().first()
    if not state:
        return {"status": "never", "running": False}
    if state["status"] == "running":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
            abandoned = cursor.fetchone()[0]
            if abandoned:
                try:
                    # The session lock is released automatically on worker termination.
                    SalesCalculatorRefresh.objects.filter(pk=1, status="running").update(
                        status="queued" if state["requested"] else "failed",
                        error="Предыдущее обновление прервано. Можно повторить обновление.")
                    state = SalesCalculatorRefresh.objects.filter(pk=1).values().get()
                finally:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
    state["running"] = state["requested"] or state["status"] in ("queued", "running")
    return state
