from django.core.management.base import BaseCommand
from datasets.services.parsers.tara_jobs import dispatch


class Command(BaseCommand):
    help = 'Dispatch Tara jobs, validate uploaded sessions and expire four-hour waits'

    def handle(self, *args, **options):
        dispatch()
