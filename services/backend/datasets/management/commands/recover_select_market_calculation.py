from django.core.management.base import BaseCommand, CommandError
from select_market.iprice_domain_models import IPriceSnapshot
from select_market.iprice_recovery import recover_calculation


class Command(BaseCommand):
    help = 'Inspect or safely fail an abandoned Select Market iPrice calculation'

    def add_arguments(self, parser):
        parser.add_argument('--snapshot-id', type=int, required=True)
        parser.add_argument('--fail', action='store_true')
        parser.add_argument('--operator', default='')
        parser.add_argument('--reason', default='')

    def handle(self, *args, **options):
        try:
            snapshot = IPriceSnapshot.objects.get(pk=options['snapshot_id'])
            if options['fail']:
                snapshot = recover_calculation(snapshot.pk, operator=options['operator'], reason=options['reason'])
            self.stdout.write(f'id={snapshot.pk} status={snapshot.status} created_at={snapshot.created_at}')
        except (IPriceSnapshot.DoesNotExist, ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
