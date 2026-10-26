"""Isolated iPrice source data; original gross prices and rounded net prices."""
from django.conf import settings
from django.db import models
from django.core.serializers.json import DjangoJSONEncoder


class IPriceLegacyArchive(models.Model):
    source_model = models.CharField(max_length=100)
    source_id = models.BigIntegerField()
    payload = models.JSONField(encoder=DjangoJSONEncoder)

    class Meta:
        db_table = '"select_market"."iprice_legacy_archive"'
        constraints = [models.UniqueConstraint(fields=['source_model', 'source_id'], name='sm_iprice_archive_source_key')]


class IPriceSourceImport(models.Model):
    kind = models.CharField(max_length=32)
    filename = models.CharField(max_length=255)
    checksum = models.CharField(max_length=64, db_index=True)
    content = models.BinaryField(editable=False)
    result = models.JSONField(default=dict)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."iprice_source_import"'
        ordering = ["-id"]


class IPricePriceImport(models.Model):
    date = models.DateField(unique=True)
    filename = models.CharField(max_length=255)
    checksum = models.CharField(max_length=64)
    rows = models.PositiveIntegerField()
    revision = models.PositiveIntegerField(default=1)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."iprice_price_import"'


class NomenclaturePrice(models.Model):
    batch = models.ForeignKey(IPricePriceImport, on_delete=models.PROTECT)
    date = models.DateField(db_index=True)
    shipp_region = models.CharField(max_length=255)
    nom = models.CharField(max_length=255, blank=True)
    code = models.CharField(max_length=160, db_index=True)
    group_1 = models.CharField(max_length=255, blank=True, default="")
    group_2 = models.CharField(max_length=255, blank=True, default="")
    group_3 = models.CharField(max_length=255, blank=True, default="")
    group_4 = models.CharField(max_length=255, blank=True, default="")
    assortment_matrix_status = models.TextField(null=True, blank=True, verbose_name="САМ")
    retail_gross = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    small_gross = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    medium_gross = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    large_gross = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    retail = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    small = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    medium = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    large = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."nomenclature_price"'
        constraints = [models.UniqueConstraint(fields=["date", "shipp_region", "code"], name="sm_iprice_price_key")]


class IPriceRegionalInput(models.Model):
    """Monthly purchase basis and explicit settings for a SKU/region, no plant."""
    month = models.DateField()
    code = models.CharField(max_length=160)
    region = models.CharField(max_length=255)
    purchase_cost = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    include_transport = models.BooleanField(default=False)
    logistics_unit = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    base_analog = models.DecimalField(max_digits=12, decimal_places=6, null=True)
    base_exclusive = models.DecimalField(max_digits=12, decimal_places=6, null=True)
    minimum_margin = models.DecimalField(max_digits=12, decimal_places=6, null=True)
    small = models.DecimalField(max_digits=7, decimal_places=6, null=True)
    medium = models.DecimalField(max_digits=7, decimal_places=6, null=True)
    large = models.DecimalField(max_digits=7, decimal_places=6, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"select_market"."iprice_regional_input"'
        constraints = [models.UniqueConstraint(fields=['month', 'code', 'region'], name='sm_iprice_regional_input_key')]
