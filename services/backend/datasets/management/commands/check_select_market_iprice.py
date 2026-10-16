"""Read-only launch checks. Does not start parsers, calculations or notifications."""
import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from organizations.models import Organization
from dashboards.models import Dashboard
from datasets.services.iprice_workspace import workspace_for
from select_market.iprice_models import IPricePriceImport, IPriceRegionalInput


class Command(BaseCommand):
    help = 'Read-only Select Market iPrice readiness report'

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError('Production readiness requires PostgreSQL')
        try:
            organization = Organization.objects.get(code='select-market')
            workspace = workspace_for(organization)
            counts = {name: workspace.model(name).objects.count() for name in (
                'NomenclaturePrice', 'BaseProductPrice', 'ParserProductClassification')}
            counts['IPriceRegionalInput'] = IPriceRegionalInput.objects.count()
            latest = IPricePriceImport.objects.order_by('-date', '-pk').first()
            # Site/classification enrich the price list; their absence does not exclude products.
            missing = [] if latest and workspace.model('NomenclaturePrice').objects.filter(batch=latest).exists() else ['NomenclaturePrice']
            purchase_count = IPriceRegionalInput.objects.filter(month=latest.date.replace(day=1), purchase_cost__gt=0).count() if latest else 0
            dashboard_exists = Dashboard.objects.filter(organization=organization, component='suc').exists()
            pending = list(workspace.model('IPriceSnapshot').objects.filter(status='building').values_list('pk', flat=True))
            report = {'schema': organization.postgres_schema, 'dashboard_exists': dashboard_exists,
                'shared_queue_enabled': bool(getattr(settings, 'PARSER_SHARED_QUEUE_ENABLED', False)),
                'counts': counts, 'missing_sources': missing, 'building_snapshots': pending,
                'purchase_rows_for_price_month': purchase_count,
                'warnings': ([name + ' is empty; products remain in calculation' for name in ('BaseProductPrice', 'ParserProductClassification') if not counts[name]]
                             + ([] if purchase_count else ['No positive purchase prices for price month; affected rows will have errors'])),
                'latest_price_date': IPricePriceImport.objects.order_by('-date').values_list('date', flat=True).first(),
                'ready_for_trial_calculation': dashboard_exists and not missing and not pending}
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        except Organization.DoesNotExist as exc:
            raise CommandError('Select Market organization is missing; check migrations') from exc
