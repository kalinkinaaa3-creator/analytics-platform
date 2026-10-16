from django.core.management.base import BaseCommand
from datasets.services.parsers.tara_jobs import execute


class Command(BaseCommand):
    help = 'Execute a claimed durable Tara job'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', required=True, type=int)
        parser.add_argument('--lease', required=True)
        parser.add_argument('--organization', choices=('iplast', 'select-market'), default='iplast')

    def handle(self, *args, **options):
        from organizations.models import Organization
        from datasets.services.iprice_workspace import workspace_for
        workspace = workspace_for(Organization.objects.get(code=options['organization'])) if options['organization'] != 'iplast' else None
        execute(options['run_id'], options['lease'], workspace=workspace)
