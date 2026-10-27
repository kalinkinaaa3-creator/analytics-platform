"""Select Market list controls, applied before pagination."""
from decimal import Decimal

from django.db.models import F, Q
from rest_framework import serializers

from datasets.services.iprice_price_analytics import ZONE_ORDER, get_active_price_zone_config
from datasets.services.iprice_workspace import IPriceWorkspace


class RowControls(serializers.Serializer):
    mode = serializers.ChoiceField(choices=['regions', 'products'], default='regions')
    zone = serializers.CharField(default='', allow_blank=True, max_length=200)
    problems_only = serializers.BooleanField(default=False)

    def validate_zone(self, value):
        zones = list(dict.fromkeys(part for part in value.split(',') if part))
        if set(zones) - set(ZONE_ORDER):
            raise serializers.ValidationError('Unknown price zone.')
        return ','.join(zones)


def regional_product_summaries(rows):
    """Product prices within the selected regional scope, before zone filtering."""
    from datasets.services.iprice_price_analytics import _build_regional_product_metrics, classify_price_zone, _deviation
    config = get_active_price_zone_config(workspace=IPriceWorkspace('select-market'))
    return {pk: {
        'current_retail_median': metrics['retail_price'],
        'effective_approved_rrp_median': metrics['final_rrp'],
        'competitor_rrp_median': metrics['market_price'],
        'zone': classify_price_zone(_deviation(metrics['final_rrp'], metrics['market_price']), config),
    } for pk, metrics in _build_regional_product_metrics(rows).items()}


def filter_rows(rows, values, *, summaries=None):
    product_mode = values['mode'] == 'products'
    prefix = 'snapshot_product__' if product_mode else ''
    if values['problems_only']:
        rows = rows.filter(Q(**{prefix + 'calculation_status__in': ['error', 'warning']}) |
                           ~Q(**{prefix + 'error_codes': []}) | ~Q(**{prefix + 'warning_codes': []}))
    zone = values['zone']
    if not zone:
        return rows
    if product_mode and summaries is not None:
        return rows.filter(snapshot_product_id__in=[pk for pk, summary in summaries.items()
                                                  if summary['zone'] in zone.split(',')])
    current = 'snapshot_product__effective_approved_rrp_median' if product_mode else 'effective_approved_rrp'
    if not product_mode:
        from datasets.services.iprice_price_analytics import _with_effective_approved_rrp
        rows = _with_effective_approved_rrp(rows)
    competitor = 'snapshot_product__competitor_rrp_median' if product_mode else 'regional_competitor_rrp_median'
    valid = Q(**{current + '__isnull': False, competitor + '__gt': 0})
    config = get_active_price_zone_config(workspace=IPriceWorkspace('select-market'))
    market = F(competitor)
    lower = market * (Decimal(1) + config['below_market_threshold'])
    upper = market * (Decimal(1) + config['above_market_threshold'])
    critical = market * (Decimal(1) + config['critical_threshold'])
    predicates = {
        'below_market': Q(**{current + '__lt': lower}),
        'in_market': Q(**{current + '__gte': lower, current + '__lte': upper}),
        'above_market': Q(**{current + '__gt': upper, current + '__lte': critical}),
        'critical_above': Q(**{current + '__gt': critical}),
    }
    selected = Q(pk__in=[])
    for key in zone.split(','):
        selected |= ~valid if key == 'no_market_data' else valid & predicates[key]
    return rows.filter(selected)
