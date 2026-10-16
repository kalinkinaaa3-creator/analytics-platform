"""Organization-local Tara execution state; global capacity is coordinated separately."""
from django.db import models

class TaraRun(models.Model):
    ACTIVE = ('queued', 'dispatching', 'running', 'waiting_session')
    origin = models.CharField(max_length=16, default='cli')
    request_key = models.CharField(max_length=255, unique=True)
    master = models.ForeignKey('select_market.ParserMasterPipelineRun', null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=24, default='queued', db_index=True)
    options = models.JSONField(default=dict)
    phase = models.CharField(max_length=24, default='products')
    error = models.TextField(blank=True, default='')
    wait_until = models.DateTimeField(null=True, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)
    resume_at = models.DateTimeField(null=True, blank=True)
    lease = models.CharField(max_length=64, blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."tararun"'

class TaraItem(models.Model):
    run = models.ForeignKey(TaraRun, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('select_market.ParserProductUrl', on_delete=models.PROTECT)
    status = models.CharField(max_length=24, default='pending', db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default='')
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('run', 'product'), name='sm_tara_run_product_unique')]
        db_table = '"select_market"."taraitem"'

class TaraCoordinator(models.Model):
    """One row serializes dispatch/upload transitions, not product requests."""
    key = models.PositiveSmallIntegerField(primary_key=True, default=1)

    class Meta:
        db_table = '"select_market"."taracoordinator"'

class TaraFetch(models.Model):
    """Short-lived page transport; never stores browser cookies."""
    run = models.ForeignKey(TaraRun, on_delete=models.CASCADE, related_name='fetches')
    run_lease = models.CharField(max_length=64)
    url = models.TextField()
    status = models.CharField(max_length=16, default='pending', db_index=True)
    token = models.CharField(max_length=64, default='')
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = '"select_market"."tarafetch"'

class TaraWorker(models.Model):
    key = models.PositiveSmallIntegerField(primary_key=True, default=1)
    owner = models.CharField(max_length=64, default='')
    heartbeat = models.DateTimeField(null=True)
    ready = models.BooleanField(default=False)

    class Meta:
        db_table = '"select_market"."taraworker"'
