from django.core.management.base import BaseCommand, CommandError
from select_market.iprice_pipeline import create_master
from datasets.services.parsers.master_pipeline_launcher import launch_parser_master_pipeline
from datasets.services.iprice_workspace import IPriceWorkspace


class Command(BaseCommand):
    help = 'Create or resume the Select Market master parser pipeline'

    def handle(self, *args, **options):
        try:
            run = create_master()
            if run.status == 'queued':
                launch_parser_master_pipeline(run.pk, workspace=IPriceWorkspace('select-market'))
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'Select Market master #{run.pk}: {run.status}')
