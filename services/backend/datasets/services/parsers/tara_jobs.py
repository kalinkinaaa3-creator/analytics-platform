"""Persistent Tara jobs. No Python/browser slot is held while waiting for a user."""
import json
import logging
import os
import subprocess
import sys
import uuid
import re
from contextlib import contextmanager
from threading import Event, Thread
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import timedelta
from pathlib import Path

import requests
from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Count, Q
from django.utils import timezone

from analytics.services.bitrix_notify import send_bitrix_message
from datasets.models import ParserMasterPipelineRun, ParserProductUrl, TaraCoordinator, TaraItem, TaraRun, TaraSession

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


def session_dir():
    directory = Path(settings.TARA_SESSION_DIR)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def browser_post(endpoint, payload, timeout=100):
    response = requests.post(
        settings.TARA_BROWSER_SERVICE_URL.rstrip('/') + endpoint,
        json=payload, headers={'X-Tara-Service-Key': settings.TARA_SERVICE_KEY}, timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


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
    counts = dict(run.items.values('status').annotate(n=Count('id')).values_list('status', 'n'))
    return {'id': run.pk, 'origin': run.origin, 'master_id': run.master_id,
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
    with transaction.atomic():
        current = TaraRun.objects.select_for_update().get(pk=run.pk)
        if current.status in TERMINAL or current.lease != run.lease:
            return
        first = current.wait_until is None
        current.status = 'waiting_session'
        current.error = message
        if first:
            current.wait_until = timezone.now() + timedelta(hours=settings.TARA_SESSION_WAIT_HOURS)
        current.lease = ''
        current.save()
        if current.master_id:
            ParserMasterPipelineRun.objects.filter(pk=current.master_id).exclude(status__in=('failed', 'cancelled', 'success')).update(status='waiting_session')
    publish(current)
    if first:
        notify(current, f'Требуется сессия Chromium. Обработано {current.items.filter(status="success").count()} из {current.items.count()}. Ожидание — 4 часа.')


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
            current.uploads.filter(status__in=('pending', 'checking')).update(
                status='rejected', error='Запуск завершён; файл не будет применён.')
        if current.master_id and status in ('failed', 'cancelled'):
            ParserMasterPipelineRun.objects.filter(pk=current.master_id).exclude(status='success').update(
                status=status, error=error, finished_at=timezone.now())
    publish(current)
    if status != 'success':
        notify(current, error)


def normalize_state(raw):
    """Accept only Tara storage, bounded and without executable/uploaded paths."""
    if len(raw) > 1024 * 1024:
        raise ValueError('Размер файла не должен превышать 1 МБ')
    try:
        data = json.loads(raw.decode('utf-8-sig'))
        cookies, origins = data['cookies'], data.get('origins', [])
        if not isinstance(cookies, list) or not isinstance(origins, list) or len(cookies) > 500:
            raise ValueError()
        result = {'cookies': [], 'origins': []}
        from urllib.parse import urlsplit
        def tara(host):
            return host == 'tara.ru' or host.endswith('.tara.ru')
        for c in cookies:
            if not isinstance(c, dict) or not tara(str(c.get('domain', '')).lstrip('.')):
                raise ValueError()
            if not all(isinstance(c.get(k), str) for k in ('name', 'value', 'domain', 'path')):
                raise ValueError()
            expiry = c.get('expires', -1)
            if not isinstance(expiry, (float, int)) or not (-1 <= expiry < 10**12):
                raise ValueError()
            same = c.get('sameSite', 'Lax')
            if same not in ('Lax', 'Strict', 'None') or not c['path'].startswith('/'):
                raise ValueError()
            result['cookies'].append({k: c[k] for k in ('name', 'value', 'domain', 'path')} | {
                'expires': expiry, 'httpOnly': bool(c.get('httpOnly')), 'secure': bool(c.get('secure')), 'sameSite': same})
        for origin in origins:
            url = urlsplit(origin['origin'])
            if url.scheme != 'https' or not tara(url.hostname or '') or url.username or url.port or url.path not in ('', '/'):
                raise ValueError()
            entries = origin.get('localStorage', [])
            if not isinstance(entries, list) or not all(isinstance(e, dict) and isinstance(e.get('name'), str) and isinstance(e.get('value'), str) for e in entries):
                raise ValueError()
            result['origins'].append({'origin': f'https://{url.hostname}', 'localStorage': entries})
        if not result['cookies']:
            raise ValueError()
        return result
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        raise ValueError('Нужен JSON экспорта Chromium с cookies и localStorage только сайта tara.ru') from None


def upload(run_id, raw, user):
    state = normalize_state(raw)
    with transaction.atomic():
        coordinator_lock()
        run = TaraRun.objects.select_for_update().get(pk=run_id)
        if run.status != 'waiting_session' or not run.wait_until or run.wait_until <= timezone.now():
            raise ValueError('Запуск уже не ожидает сессию или срок ожидания истёк')
        if run.uploads.filter(status__in=('pending', 'checking')).exists():
            raise ValueError('Предыдущий файл ещё проверяется')
        filename = uuid.uuid4().hex + '.json'
        target = session_dir() / filename
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf8') as stream:
            json.dump(state, stream, ensure_ascii=False)
        try:
            candidate = TaraSession.objects.create(run=run, filename=filename, uploaded_by=user)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    kick()
    return candidate


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


def check_session(candidate):
    run = candidate.run
    urls = list(run.items.filter(status='pending').values_list('product__url', flat=True)[:3])
    if not urls:
        urls = list(ParserProductUrl.objects.filter(source='tara', status='active').values_list('url', flat=True)[:3])
    result = browser_post('/session/check', {'session': candidate.filename, 'urls': urls}, timeout=240) if urls else {'valid': True}
    with transaction.atomic():
        coordinator_lock()
        run = TaraRun.objects.select_for_update().get(pk=run.pk)
        current = TaraSession.objects.select_for_update().get(pk=candidate.pk)
        if current.status != 'checking':
            return
        valid = result.get('valid') is True and run.status == 'waiting_session' and run.wait_until and run.wait_until > timezone.now()
        current.status = 'valid' if valid else 'rejected'
        current.error = '' if valid else 'Доступ не подтверждён. Проверьте файл, доступность сайта и срок ожидания.'
        current.checked_at = timezone.now()
        current.save()
        if valid:
            run.session, run.status, run.error = current, 'queued', ''
            run.wait_until = None
            run.save()
            if run.master_id:
                ParserMasterPipelineRun.objects.filter(pk=run.master_id, status='waiting_session').update(status='waiting_tara')
    publish(run)
    if valid:
        notify(run, 'Сессия принята. Загрузка продолжится автоматически.')
    else:
        (session_dir() / candidate.filename).unlink(missing_ok=True)


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
    """Called on upload and by a one-minute maintenance DAG. Claims are durable."""
    now = timezone.now()
    cleanup_sessions()
    for run in TaraRun.objects.filter(status='waiting_session', wait_until__lte=now):
        finish(run, 'failed', 'Истекли 4 часа ожидания сессии Тары. Сохранённые данные остаются доступными.')
    candidate = None
    with transaction.atomic():
        coordinator_lock()
        # Recover dispatch/validation after container failure; requests have bounded timeouts.
        TaraSession.objects.filter(status='checking', checked_at__lt=now - timedelta(minutes=6)).update(status='pending')
        for stale in TaraRun.objects.select_for_update().filter(status__in=('running', 'dispatching'), heartbeat__lt=now - timedelta(minutes=6)):
            stale.items.filter(status='running').update(status='pending')
            stale.status, stale.lease = 'queued', ''
            stale.save()
        candidate = TaraSession.objects.filter(status='pending', run__status='waiting_session', run__wait_until__gt=now).order_by('id').first()
        if candidate:
            candidate.status, candidate.checked_at = 'checking', now
            candidate.save()
    if candidate:
        try:
            check_session(candidate)
        except Exception:
            logger.exception('Session validation service failed')
            TaraSession.objects.filter(pk=candidate.pk, status='checking').update(
                status='rejected', error='Сервис проверки недоступен. Повторите загрузку.', checked_at=timezone.now())
            (session_dir() / candidate.filename).unlink(missing_ok=True)
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


@transaction.atomic
def cleanup_sessions():
    """Remove only our named session files, never user files or active generations."""
    coordinator_lock()
    cutoff = timezone.now() - timedelta(days=getattr(settings, 'TARA_SESSION_RETENTION_DAYS', 7))
    candidates = TaraSession.objects.filter(created_at__lt=cutoff).exclude(
        status__in=('pending', 'checking', 'expired')).exclude(
        executions__status__in=TaraRun.ACTIVE).exclude(run__status__in=TaraRun.ACTIVE)
    for candidate in candidates.distinct():
        if not re.fullmatch(r'[a-f0-9]{32}\.json', candidate.filename):
            continue
        root = session_dir().resolve()
        files = [root / candidate.filename] + [root / 'workers' / candidate.filename / f'{i}.json' for i in range(1, 6)]
        for file in files:
            if file.resolve().is_relative_to(root):
                file.unlink(missing_ok=True)
        TaraSession.objects.filter(pk=candidate.pk).update(status='expired')


def process_item(item_id, run_id, lease, filename):
    from datasets.services.parsers.tara_product_parser import (
        fetch_html_via_browser, parse_properties, parse_price_rows, save_product_data,
        BrowserBlockedError, BrowserTransportError, ProductNotFoundError, mark_url_not_found, mark_url_failed,
    )
    close_old_connections()
    item = TaraItem.objects.select_related('product').get(pk=item_id)
    try:
        html = fetch_html_via_browser(item.product.url, session=filename)
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
        if run.phase == 'sitemap':
            from datasets.services.parsers.tara_sitemap import sync_tara_sitemap_to_product_urls
            with keep_alive(run.pk, lease):
                sync_tara_sitemap_to_product_urls(session=run.session.filename if run.session_id else None)
            with transaction.atomic():
                current = TaraRun.objects.select_for_update().get(pk=run.pk)
                if current.lease != lease or current.status != 'running':
                    return
                populate(run)
                run.phase = 'products'
                run.save(update_fields=['phase'])
        if run.items.filter(status='pending').exists() and not run.session_id:
            # Reuse a validated state if available; real requests determine access.
            recent = TaraSession.objects.filter(status='valid').order_by('-id').first()
            if recent and (session_dir() / recent.filename).exists():
                run.session = recent
                run.save(update_fields=['session'])
            else:
                set_waiting(run, 'Для загрузки Тары требуется сессия Chromium')
                return
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
                    pending.add(pool.submit(process_item, item.pk, run.pk, lease, run.session.filename))
                if not pending:
                    break
                done, pending = wait(pending, timeout=5, return_when=FIRST_COMPLETED)
                for future in done:
                    outcome = future.result()
                    blocked = outcome == 'blocked' or blocked
                    unavailable = outcome == 'unavailable' or unavailable
            # Context manager drains the at most five in-flight requests.
        if blocked:
            set_waiting(run, 'Сайт ограничил доступ. Загрузите новую сессию Chromium.')
            return
        if unavailable:
            finish(run, 'failed', 'Браузерный сервис недоступен. Проверьте контейнер и внутренний ключ доступа; новый файл сессии не требуется.')
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
            set_waiting(run, 'Сайт ограничил доступ к sitemap. Требуется сессия Chromium.')
            return
        logger.exception('Tara job %s failed', run.pk)
        finish(run, 'failed', 'Ошибка выполнения Тары. Подробности в журнале tara_jobs.log.')
    finally:
        kick()
