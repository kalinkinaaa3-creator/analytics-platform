from django.core.management.base import BaseCommand
from datasets.services.parsers.tara_jobs import execute


class Command(BaseCommand):
    help = 'Execute a claimed durable Tara job'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', required=True, type=int)
        parser.add_argument('--lease', required=True)

    def handle(self, *args, **options):
        execute(options['run_id'], options['lease'])
