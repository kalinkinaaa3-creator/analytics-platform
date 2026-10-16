"""Background execution with a consistent PostgreSQL view of calculation inputs."""
import logging
from django.db import connection, transaction
from django.utils import timezone
from datasets.services.iprice_snapshot_builder import build_created_iprice_snapshot
from .iprice_domain_models import IPriceSnapshot

logger = logging.getLogger('iprice.select_market')


def run_calculation(snapshot_id):
    # This service is a top-level worker transaction, never an HTTP request job.
    if connection.vendor == 'postgresql' and connection.in_atomic_block:
        raise RuntimeError('Calculation requires its own database transaction')
    acquired = False
    try:
        with transaction.atomic():
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                    cursor.execute('SELECT pg_try_advisory_xact_lock(%s, %s)', [1936289907, 1])
                    if not cursor.fetchone()[0]:
                        return {'status': 'already_running'}
            snapshot = IPriceSnapshot.objects.select_for_update().get(pk=snapshot_id)
            if snapshot.status != 'building':
                return {'status': snapshot.status}
            acquired = True
            snapshot.parameters = {**snapshot.parameters, 'worker_started_at': timezone.now().isoformat(),
                'input_read_mode': 'repeatable_read' if connection.vendor == 'postgresql' else 'test_transaction'}
            snapshot.save(update_fields=['parameters'])
            return build_created_iprice_snapshot(snapshot=snapshot)
    except Exception as exc:
        # The failed build transaction is rolled back: no half-built version is exposed.
        # Retain the previous current version; never overwrite another terminal state.
        if acquired:
            IPriceSnapshot.objects.filter(pk=snapshot_id, status='building').update(
                status='failed', is_current=False, finished_at=timezone.now(), error=str(exc)[:4000])
        logger.exception('Select Market calculation %s failed', snapshot_id)
        raise
