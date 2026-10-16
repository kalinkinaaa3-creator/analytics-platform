from django.core.management.base import BaseCommand
from datasets.services.parsers.tara_jobs import dispatch


class Command(BaseCommand):
    help = 'Dispatch Tara jobs, validate uploaded sessions and expire four-hour waits'

    def handle(self, *args, **options):
        dispatch()
        from datasets.services.parsers.queue_execution import enabled
        from datasets.services.iprice_workspace import workspace_for
        from organizations.models import Organization
        if enabled():
            organization = Organization.objects.filter(code='select-market').first()
            if organization:
                dispatch(workspace=workspace_for(organization))
