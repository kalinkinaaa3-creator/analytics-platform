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


def worker_workspace():
    """The server chooses the organization from the occupied slot, never the worker."""
    if not getattr(settings, 'PARSER_SHARED_QUEUE_ENABLED', False):
        return None
    from datasets.parser_queue_models import ParserQueueEntry
    from datasets.services.iprice_workspace import workspace_for
    entry = ParserQueueEntry.objects.filter(status__in=('running', 'waiting_remote')).select_related('organization').first()
    return workspace_for(entry.organization) if entry and entry.organization.code == 'select-market' else None


def result_workspace(task_id, token):
    """Old workers echo the token; it disambiguates equal IDs without protocol changes."""
    if not isinstance(token, str) or len(token) != 32:
        raise ValueError('Invalid task token')
    if not getattr(settings, 'PARSER_SHARED_QUEUE_ENABLED', False):
        return None
    from datasets.services.iprice_workspace import IPriceWorkspace
    local = IPriceWorkspace('select-market')
    matches = [workspace for workspace, model in ((None, TaraFetch), (local, local.model('TaraFetch')))
               if model.objects.filter(pk=task_id, token=token).exists()]
    if len(matches) != 1:
        raise ValueError('Unknown or ambiguous task token')
    return matches[0]




def allowed_url(url):
    try:
        u = urlsplit(url)
        return u.scheme == 'https' and not u.username and not u.password and u.port in (None, 443) and (
            u.hostname == 'tara.ru' or (u.hostname or '').endswith('.tara.ru'))
    except (ValueError, TypeError):
        return False


def available():
    return TaraWorker.objects.filter(pk=1, ready=True, heartbeat__gt=timezone.now()-timedelta(seconds=90)).exists()


def _require_capacity(run, workspace):
    if workspace is None or workspace.code == 'iplast':
        return
    from datasets.parser_queue_models import ParserQueueEntry
    if not getattr(settings, 'PARSER_SHARED_QUEUE_ENABLED', False):
        raise ValueError('Shared parser queue is disabled')
    kind, run_id = ('master', run.master_id) if run.master_id else ('tara', run.pk)
    if not ParserQueueEntry.objects.filter(organization__code=workspace.code,
            kind=kind, run_id=run_id, status__in=('running', 'waiting_remote')).exists():
        raise ValueError('Tara run does not own shared parser capacity')


def fetch(url, *, workspace=None, run_id=None, run_lease=None):
    TaraRun = workspace.model("TaraRun") if workspace else globals()["TaraRun"]
    TaraFetch = workspace.model("TaraFetch") if workspace else globals()["TaraFetch"]
    from .tara_product_parser import BrowserBlockedError
    if not allowed_url(url) or not available():
        raise BrowserBlockedError('Windows executor is unavailable')
    runs = TaraRun.objects.filter(status='running')
    if run_id is not None:
        runs = runs.filter(pk=run_id, lease=run_lease)
    run = runs.first()
    if not run:
        raise BrowserBlockedError('No active Tara run')
    _require_capacity(run, workspace)
    task = TaraFetch.objects.create(run=run, run_lease=run.lease, url=url,
                                   expires_at=timezone.now()+timedelta(seconds=360))
    try:
        deadline = time.monotonic()+360
        while time.monotonic() < deadline:
            if not TaraRun.objects.filter(pk=run.pk, lease=run.lease, status='running').exists():
                raise BrowserBlockedError('Run no longer active')
            _require_capacity(run, workspace)
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
def claim(owner, ready, pull=True, *, workspace=None):
    TaraRun = workspace.model("TaraRun") if workspace else globals()["TaraRun"]
    TaraFetch = workspace.model("TaraFetch") if workspace else globals()["TaraFetch"]
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
    if getattr(settings, 'PARSER_SHARED_QUEUE_ENABLED', False):
        from datasets.services.iprice_workspace import IPriceWorkspace
        other = IPriceWorkspace('iplast' if workspace and workspace.code == 'select-market' else 'select-market')
        count += other.model('TaraFetch').objects.filter(status='claimed', expires_at__gt=now).count()
    tasks = list(TaraFetch.objects.select_for_update().filter(status='pending', expires_at__gt=now,
                 run__status='running').order_by('id')[:max(0,5-count)])
    result = []
    for task in tasks:
        _require_capacity(task.run, workspace)
        if task.run.lease != task.run_lease:
            task.status = 'expired'
        else:
            task.status, task.token = 'claimed', uuid.uuid4().hex
            result.append({'id': task.pk, 'url': task.url, 'token': task.token})
        task.save(update_fields=['status','token'])
    return result


@transaction.atomic
def complete(task_id, token, payload, *, workspace=None):
    TaraRun = workspace.model("TaraRun") if workspace else globals()["TaraRun"]
    TaraFetch = workspace.model("TaraFetch") if workspace else globals()["TaraFetch"]
    task = TaraFetch.objects.select_for_update().get(pk=task_id)
    run = TaraRun.objects.select_for_update().get(pk=task.run_id)
    _require_capacity(run, workspace)
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
