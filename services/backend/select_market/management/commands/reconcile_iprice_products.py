from django.core.management.base import BaseCommand, CommandError
from select_market.iprice_registry import reconcile


class Command(BaseCommand):
    help = 'Validate and bind Select Market own-product IDs. Default: rollback, no data published.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Commit the validated changes')

    def handle(self, *args, **options):
        try:
            result = reconcile(apply=options['apply'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(('APPLIED' if options['apply'] else 'DRY RUN (rolled back)') + ': ' + str(result))
