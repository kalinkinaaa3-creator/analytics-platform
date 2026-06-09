from django.db.models.signals import post_save
from django.dispatch import receiver

from datasets.models import Dataset

from datasets.services.csv_loader import load_csv


@receiver(post_save, sender=Dataset)
def dataset_uploaded(sender, instance, created, **kwargs):

    if created:
        load_csv(instance)