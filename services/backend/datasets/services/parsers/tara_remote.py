"""Bounded Windows page transport. Existing server parser owns all data writes."""
import time
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from datasets.models import TaraFetch, TaraWorker, TaraRun




def allowed_url(url):
    try:
        u = urlsplit(url)
        return u.scheme == 'https' and not u.username and not u.password and u.port in (None, 443) and (
            u.hostname == 'tara.ru' or (u.hostname or '').endswith('.tara.ru'))
    except (ValueError, TypeError):
        return False


def available():
    return TaraWorker.objects.filter(pk=1, ready=True, heartbeat__gt=timezone.now()-timedelta(seconds=90)).exists()


def fetch(url):
    from .tara_product_parser import BrowserBlockedError
    if not allowed_url(url) or not available():
        raise BrowserBlockedError('Windows executor is unavailable')
    run = TaraRun.objects.filter(status='running').first()
    if not run:
        raise BrowserBlockedError('No active Tara run')
    task = TaraFetch.objects.create(run=run, run_lease=run.lease, url=url,
                                   expires_at=timezone.now()+timedelta(seconds=360))
    try:
        deadline = time.monotonic()+360
        while time.monotonic() < deadline:
            if not TaraRun.objects.filter(pk=run.pk, lease=run.lease, status='running').exists():
                raise BrowserBlockedError('Run no longer active')
            task.refresh_from_db()
            if task.status == 'done':
                return task.payload
            if not available():
                raise BrowserBlockedError('Windows executor disconnected')
            time.sleep(1)
        raise BrowserBlockedError('Windows executor response timed out')
    finally:
        TaraFetch.objects.filter(pk=task.pk).update(status='expired', payload={})


@transaction.atomic
def claim(owner, ready, pull=True):
    from .tara_jobs import coordinator_lock
    coordinator_lock()
    now = timezone.now()
    worker, _ = TaraWorker.objects.get_or_create(pk=1)
    if worker.owner != owner and worker.heartbeat and worker.heartbeat > now-timedelta(seconds=90):
        raise ValueError('Another Windows executor is active')
    worker.owner, worker.ready, worker.heartbeat = owner, ready, now
    worker.save()
    TaraFetch.objects.filter(expires_at__lte=now).exclude(status='expired').update(status='expired', payload={})
    TaraFetch.objects.exclude(run__status='running').exclude(status='expired').update(status='expired', payload={})
    TaraFetch.objects.exclude(run_lease=F('run__lease')).exclude(status='expired').update(status='expired', payload={})
    TaraFetch.objects.filter(created_at__lt=now-timedelta(days=1)).delete()
    if not ready or not pull:
        return []
    # Resume the same run, never replace its progress or extend the waiting deadline.
    TaraRun.objects.filter(status='waiting_session', wait_until__gt=now).update(status='queued', error='')
    count = TaraFetch.objects.filter(status='claimed', expires_at__gt=now).count()
    tasks = list(TaraFetch.objects.select_for_update().filter(status='pending', expires_at__gt=now,
                 run__status='running').order_by('id')[:max(0,5-count)])
    result = []
    for task in tasks:
        if task.run.lease != task.run_lease:
            task.status = 'expired'
        else:
            task.status, task.token = 'claimed', uuid.uuid4().hex
            result.append({'id': task.pk, 'url': task.url, 'token': task.token})
        task.save(update_fields=['status','token'])
    return result


@transaction.atomic
def complete(task_id, token, payload):
    task = TaraFetch.objects.select_for_update().get(pk=task_id)
    run = TaraRun.objects.select_for_update().get(pk=task.run_id)
    if task.token != token or task.expires_at <= timezone.now() or run.status != 'running' or run.lease != task.run_lease:
        raise ValueError('Expired task')
    if task.status == 'done':
        return
    if task.status != 'claimed':
        raise ValueError('Task not claimed')
    if not isinstance(payload, dict) or type(payload.get('status')) is not int or not 100 <= payload['status'] <= 599:
        raise ValueError('Invalid HTTP status')
    html = payload.get('html', '')
    if not isinstance(html, str) or len(html.encode('utf-8')) > 8*1024*1024:
        raise ValueError('Response too large')
    final = payload.get('final_url')
    if not isinstance(final,str) or not allowed_url(final) or len(final)>8192:
        raise ValueError('Invalid final URL')
    # Reject redirects for XML as well as product cards; no cookie/header fields accepted.
    if final != task.url:
        raise ValueError('Unexpected redirect')
    task.payload = {'status': payload['status'], 'html': html, 'final_url': final,
                    'blocked': payload.get('blocked') is True,
                    'error': ('request_exhausted' if payload.get('error') == 'request_exhausted'
                              else 'transport' if payload.get('error') else None)}
    task.status = 'done'
    task.save(update_fields=['payload','status'])
