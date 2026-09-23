"""Persistent Tara jobs. No Python/browser slot is held while waiting for a user."""
import logging
import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from threading import Event, Thread
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Count, Q
from django.utils import timezone

from analytics.services.bitrix_notify import send_bitrix_message
from datasets.models import ParserMasterPipelineRun, ParserProductUrl, TaraCoordinator, TaraItem, TaraRun

logger = logging.getLogger('parsers.tara')
TERMINAL = ('success', 'failed', 'cancelled')


class TaraPending(Exception):
    pass


@contextmanager
def keep_alive(run_id, lease):
    """Keep synchronous sitemap/image work from being reclaimed as a dead job."""
    stopped = Event()

    def pulse():
        try:
            while not stopped.wait(30):
                close_old_connections()
                if not TaraRun.objects.filter(pk=run_id, lease=lease, status='running').update(heartbeat=timezone.now()):
                    break
        except Exception:
            logger.exception('Tara heartbeat failed for run %s', run_id)
        finally:
            close_old_connections()

    thread = Thread(target=pulse, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=5)


def coordinator_lock():
    TaraCoordinator.objects.get_or_create(pk=1)
    return TaraCoordinator.objects.select_for_update().get(pk=1)






def notify(run, message):
    try:
        send_bitrix_message(
            f'[b]Тара: запуск #{run.pk}[/b]\n{message}\n{settings.TARA_DASHBOARD_URL}',
            logger_name='parsers.tara',
        )
    except Exception:
        logger.exception('Tara notification failed for run %s', run.pk)


def publish(run):
    from datasets.services.iprice_runtime import publish_iprice_update
    try:
        publish_iprice_update('parser_tara_progress', run_id=run.master_id,
                             tara_run_id=run.pk, status=run.status, invalidate_health=run.status in TERMINAL)
    except Exception:
        logger.exception('Tara event failed')


def progress(run):
    from .tara_remote import available
    counts = dict(run.items.values('status').annotate(n=Count('id')).values_list('status', 'n'))
    return {'id': run.pk, 'origin': run.origin, 'master_id': run.master_id,
            'execution_mode': 'windows',
            'worker_ready': available(),
            'status': run.status, 'phase': run.phase, 'error': run.error,
            'counts': counts, 'total': sum(counts.values()), 'wait_until': run.wait_until,
            'started_at': run.started_at, 'finished_at': run.finished_at,
            'classified_only': bool(run.options.get('classified_only'))}


def create_run(*, request_key, origin='cli', master_id=None, options=None):
    options = dict(options or {})
    with transaction.atomic():
        coordinator_lock()
        existing = TaraRun.objects.filter(request_key=request_key).first()
        if existing:
            return existing
        if TaraRun.objects.filter(status__in=TaraRun.ACTIVE).exists():
            raise TaraPending('Другой запуск Тары ещё не завершён')
        run = TaraRun.objects.create(request_key=request_key, origin=origin,
                                     master_id=master_id, options=options,
                                     phase='sitemap' if options.get('sitemap') else 'products')
        if run.phase == 'products':
            populate(run)
        return run


def populate(run):
    """Exactly the existing daily/classification selection; evaluated once."""
    from datasets.services.parsers.product_key_selector import get_active_classified_product_keys
    qs = ParserProductUrl.objects.filter(source='tara', status=ParserProductUrl.STATUS_ACTIVE)
    opts = run.options
    if opts.get('classified_only'):
        qs = qs.filter(id__in=get_active_classified_product_keys('tara'))
    if opts.get('retry_failed'):
        qs = qs.filter(is_loaded=False, last_error__isnull=False)
        if run.master_id:
            previous = TaraRun.objects.filter(master_id=run.master_id).exclude(pk=run.pk).order_by('-id').first()
            if previous:
                qs = qs.filter(id__in=previous.items.filter(status='error').values('product_id'))
    elif opts.get('blocked_only'):
        qs = qs.filter(is_loaded=False, last_error__icontains='blocked')
    else:
        qs = qs.filter(Q(is_loaded=False) | Q(date_update__date__lt=timezone.localdate()) | Q(date_update__isnull=True))
    ids = list(qs.order_by('id').values_list('id', flat=True))
    if opts.get('limit'):
        ids = ids[:int(opts['limit'])]
    TaraItem.objects.bulk_create([TaraItem(run=run, product_id=pk) for pk in ids], batch_size=500)


def set_waiting(run, message):
    message = 'Ожидается Windows-исполнитель. Откройте служебную вкладку Chromium и запустите исполнитель.'
    with transaction.atomic():
        current = TaraRun.objects.select_for_update().get(pk=run.pk)
        if current.status in TERMINAL or current.lease != run.lease:
            return
        first = current.wait_until is None
        current.status = 'waiting_session'
        current.error = message
        if first:
            current.wait_until = timezone.now() + timedelta(hours=settings.TARA_WORKER_WAIT_HOURS)
        current.lease = ''
        current.save()
        if current.master_id:
            ParserMasterPipelineRun.objects.filter(pk=current.master_id).exclude(status__in=('failed', 'cancelled', 'success')).update(status='waiting_session')
    publish(current)
    if first:
        notify(current, message)


def finish(run, status, error='', *, force=False):
    with transaction.atomic():
        current = TaraRun.objects.select_for_update().get(pk=run.pk)
        if current.status in TERMINAL:
            return
        if not force and run.lease and current.lease != run.lease:
            return
        current.status, current.error = status, error
        current.finished_at, current.lease = timezone.now(), ''
        current.save()
        if status in ('failed', 'cancelled'):
            current.items.filter(status='running').update(status='pending')
        if current.master_id and status in ('failed', 'cancelled'):
            ParserMasterPipelineRun.objects.filter(pk=current.master_id).exclude(status='success').update(
                status=status, error=error, finished_at=timezone.now())
    publish(current)
    if status != 'success':
        notify(current, error)






def launch(command, *args):
    logs = Path(settings.BASE_DIR) / 'logs'
    logs.mkdir(exist_ok=True)
    with (logs / 'tara_jobs.log').open('a', encoding='utf8') as stream:
        subprocess.Popen([sys.executable, str(Path(settings.BASE_DIR) / 'manage.py'), command, *map(str, args)],
                         cwd=settings.BASE_DIR, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                         start_new_session=True, env=os.environ.copy())


def kick():
    try:
        launch('process_tara_jobs')
    except OSError:
        logger.exception('Dispatcher launch failed; periodic dispatcher will retry')




def recover_master_processes():
    """A released OS lock distinguishes a crashed master from a slow live one."""
    if os.name != 'posix':
        return
    import fcntl
    lock_dir = Path(settings.BASE_DIR) / 'private' / 'parser-locks'
    lock_dir.mkdir(parents=True, exist_ok=True)
    for parent in ParserMasterPipelineRun.objects.filter(status='running', current_step__startswith='tara_'):
        with (lock_dir / f'master-{parent.pk}.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            child = TaraRun.objects.filter(master=parent).order_by('-id').first()
            if child and child.status in ('failed', 'cancelled'):
                ParserMasterPipelineRun.objects.filter(pk=parent.pk, status='running').update(
                    status=child.status, error=child.error, finished_at=timezone.now())
            else:
                status = 'waiting_session' if child and child.status == 'waiting_session' else 'waiting_tara'
                ParserMasterPipelineRun.objects.filter(pk=parent.pk, status='running').update(status=status)


def dispatch():
    """Called when executor connects and by the maintenance DAG."""
    now = timezone.now()
    for run in TaraRun.objects.filter(status='waiting_session', wait_until__lte=now):
        finish(run, 'failed', 'Истекли 4 часа ожидания Windows-исполнителя Тары. Сохранённые данные остаются доступными.')
    with transaction.atomic():
        coordinator_lock()
        # Recover dispatch after container failure; requests have bounded timeouts.
        for stale in TaraRun.objects.select_for_update().filter(status__in=('running', 'dispatching'), heartbeat__lt=now - timedelta(minutes=6)):
            stale.items.filter(status='running').update(status='pending')
            stale.status, stale.lease = 'queued', ''
            stale.save()
    with transaction.atomic():
        coordinator_lock()
        run = TaraRun.objects.select_for_update().filter(status='queued').filter(Q(resume_at__isnull=True) | Q(resume_at__lte=timezone.now())).order_by('id').first()
        if run:
            run.status, run.lease, run.heartbeat = 'dispatching', uuid.uuid4().hex, timezone.now()
            run.save()
            transaction.on_commit(lambda: launch('run_tara_job', '--run-id', run.pk, '--lease', run.lease))
    # Masters park at the Tara step. Resume only when their child is terminal or
    # no child could be created because a different origin owned Tara.
    from datasets.services.parsers.master_pipeline_launcher import launch_parser_master_pipeline
    from django.utils.dateparse import parse_datetime
    recover_master_processes()
    for parent in ParserMasterPipelineRun.objects.filter(status='queued', current_step__startswith='tara_'):
        last = parse_datetime(parent.result.get('resume_dispatched_at', ''))
        if last and last < timezone.now() - timedelta(minutes=6):
            ParserMasterPipelineRun.objects.filter(pk=parent.pk, status='queued').update(status='waiting_tara')
    for master in ParserMasterPipelineRun.objects.filter(status__in=('waiting_tara', 'waiting_session')):
        child = TaraRun.objects.filter(master=master).order_by('-id').first()
        # If the next retry step could not claim Tara, the previous successful
        # child alone must not cause repeated spawning while another run owns it.
        ready = child and child.status == 'success' and not TaraRun.objects.filter(status__in=TaraRun.ACTIVE).exists()
        if not child and not TaraRun.objects.filter(status__in=TaraRun.ACTIVE).exists():
            ready = True
        if ready and ParserMasterPipelineRun.objects.filter(pk=master.pk, status__in=('waiting_tara', 'waiting_session')).update(status='queued'):
            master.result = {**master.result, 'resume_dispatched_at': timezone.now().isoformat()}
            ParserMasterPipelineRun.objects.filter(pk=master.pk).update(result=master.result)
            try:
                launch_parser_master_pipeline(master.pk)
            except Exception:
                ParserMasterPipelineRun.objects.filter(pk=master.pk, status='queued').update(status='waiting_tara')
                logger.exception('Master resume launch failed')




def process_item(item_id, run_id, lease):
    from datasets.services.parsers.tara_product_parser import (
        fetch_html_via_browser, parse_properties, parse_price_rows, save_product_data,
        BrowserBlockedError, BrowserTransportError, ProductNotFoundError, mark_url_not_found, mark_url_failed,
    )
    close_old_connections()
    item = TaraItem.objects.select_related('product').get(pk=item_id)
    try:
        html = fetch_html_via_browser(item.product.url)
        properties = parse_properties(html)
        prices = parse_price_rows(html, item.product.url)
        with transaction.atomic():
            run = TaraRun.objects.select_for_update().get(pk=run_id)
            if run.lease != lease or run.status != 'running':
                return 'stale'
            save_product_data(item.product, properties, prices)
            item.status, item.finished_at = 'success', timezone.now()
            item.error = ''
            item.save()
        return 'success'
    except Exception as exc:
        with transaction.atomic():
            run = TaraRun.objects.select_for_update().get(pk=run_id)
            if run.lease != lease or run.status != 'running':
                return 'stale'
            if isinstance(exc, (BrowserBlockedError, BrowserTransportError)):
                item.status = 'pending'
            elif isinstance(exc, ProductNotFoundError):
                mark_url_not_found(item.product_id, exc)
                item.status = 'not_found'
            else:
                mark_url_failed(item.product_id, exc)
                item.status = 'error'
            item.error = str(exc)[:1000]
            item.save()
        if isinstance(exc, BrowserTransportError):
            return 'unavailable'
        return 'blocked' if isinstance(exc, BrowserBlockedError) else item.status
    finally:
        close_old_connections()


def execute(run_id, lease):
    from .tara_remote import available
    from datasets.services.parsers.product_image_sync import sync_parser_source_images
    run = TaraRun.objects.get(pk=run_id)
    if not TaraRun.objects.filter(pk=run_id, lease=lease, status='dispatching').update(
        status='running', heartbeat=timezone.now()):
        return
    run.refresh_from_db()
    if not run.started_at:
        run.started_at = timezone.now()
        run.save(update_fields=['started_at'])
    try:
        if not available():
            set_waiting(run, 'Windows executor unavailable')
            return
        if run.phase == 'sitemap':
            from datasets.services.parsers.tara_sitemap import sync_tara_sitemap_to_product_urls
            with keep_alive(run.pk, lease):
                sync_tara_sitemap_to_product_urls()
            with transaction.atomic():
                current = TaraRun.objects.select_for_update().get(pk=run.pk)
                if current.lease != lease or current.status != 'running':
                    return
                if run.options.get('sitemap_only'):
                    finish(run, 'success')
                    return
                populate(run)
                run.phase = 'products'
                run.save(update_fields=['phase'])
        workers = max(1, min(5, int(run.options.get('workers') or settings.TARA_PARSER_WORKERS)))
        blocked = False
        unavailable = False
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = set()
            while True:
                if not TaraRun.objects.filter(pk=run.pk, lease=lease, status='running').update(heartbeat=timezone.now()):
                    break
                while not blocked and not unavailable and len(pending) < workers:
                    with transaction.atomic():
                        owner = TaraRun.objects.select_for_update().get(pk=run.pk)
                        if owner.lease != lease or owner.status != 'running':
                            break
                        item = run.items.filter(status='pending').order_by('id').first()
                        if not item:
                            break
                        item.status, item.attempts = 'running', item.attempts + 1
                        item.save(update_fields=['status', 'attempts'])
                    pending.add(pool.submit(process_item, item.pk, run.pk, lease))
                if not pending:
                    break
                done, pending = wait(pending, timeout=5, return_when=FIRST_COMPLETED)
                for future in done:
                    outcome = future.result()
                    blocked = outcome == 'blocked' or blocked
                    unavailable = outcome == 'unavailable' or unavailable
            # Context manager drains the at most five in-flight requests.
        if blocked:
            set_waiting(run, 'Windows executor needs browser recovery')
            return
        if unavailable:
            set_waiting(run, 'Windows executor unavailable')
            return
        run.refresh_from_db()
        if run.lease != lease or run.status != 'running':
            return
        if run.options.get('dag_retry') and run.phase == 'products' and run.items.filter(status='error').exists():
            run.items.filter(status='error').update(status='pending')
            run.phase, run.status, run.lease = 'retry', 'queued', ''
            run.resume_at = timezone.now() + timedelta(minutes=20)
            run.save()
            return
        with keep_alive(run.pk, lease):
            sync_parser_source_images('tara')
        finish(run, 'success')
        if not run.master_id:
            counts = progress(run)['counts']
            notify(run, f'Обход завершён. Успешно: {counts.get("success", 0)}, 404: {counts.get("not_found", 0)}, ошибок: {counts.get("error", 0)}.')
    except Exception as exc:
        from .tara_product_parser import BrowserBlockedError
        if isinstance(exc, BrowserBlockedError):
            set_waiting(run, 'Windows executor needs sitemap access')
            return
        logger.exception('Tara job %s failed', run.pk)
        finish(run, 'failed', 'Ошибка выполнения Тары. Подробности в журнале tara_jobs.log.')
    finally:
        kick()
