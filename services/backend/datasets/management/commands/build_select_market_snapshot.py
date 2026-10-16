from django.core.management.base import BaseCommand, CommandError
from select_market.iprice_calculation import run_calculation


class Command(BaseCommand):
    help = 'Build an existing Select Market calculation in a consistent transaction'

    def add_arguments(self, parser):
        parser.add_argument('--snapshot-id', type=int, required=True)

    def handle(self, *args, **options):
        try:
            result = run_calculation(options['snapshot_id'])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(str(result))
