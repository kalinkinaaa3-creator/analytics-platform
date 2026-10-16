"""Fail an abandoned calculation only after obtaining the worker's database lock."""
from django.db import connection, transaction
from django.utils import timezone
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.iprice_snapshot_builder import _lock_snapshot_workspace
from .iprice_domain_models import IPriceSnapshot


def acquire_worker_lock():
    if connection.vendor != 'postgresql':
        raise RuntimeError('Recovery requires PostgreSQL advisory locks')
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_xact_lock(%s, %s)', [1936289907, 1])
        if not cursor.fetchone()[0]:
            raise ValueError('Calculation worker is still running; recovery refused')


def recover_calculation(snapshot_id, *, reason, operator):
    if not reason.strip() or not operator.strip():
        raise ValueError('Reason and operator are required')
    with transaction.atomic():
        acquire_worker_lock()
        _lock_snapshot_workspace(IPriceWorkspace('select-market'))
        snapshot = IPriceSnapshot.objects.select_for_update().get(pk=snapshot_id)
        if snapshot.status != 'building':
            raise ValueError('Only a building snapshot can be recovered')
        snapshot.status = 'failed'
        snapshot.is_current = False
        snapshot.finished_at = timezone.now()
        snapshot.error = 'Calculation stopped by administrative recovery'
        snapshot.parameters = {**snapshot.parameters, 'recovery': {
            'operator': operator, 'reason': reason, 'at': snapshot.finished_at.isoformat()}}
        snapshot.save(update_fields=['status', 'is_current', 'finished_at', 'error', 'parameters'])
        return snapshot
