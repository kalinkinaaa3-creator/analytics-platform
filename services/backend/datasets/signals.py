from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache

from datasets.models import Dataset

from datasets.services.csv_loader import load_csv
from analytics.services.clickhouse_sync import sync_dataset_to_clickhouse


@receiver(post_save, sender=Dataset)
def dataset_uploaded(sender, instance, created, **kwargs):

    if created:
        load_csv(instance)
        sync_dataset_to_clickhouse(instance.id)

        cache.clear()