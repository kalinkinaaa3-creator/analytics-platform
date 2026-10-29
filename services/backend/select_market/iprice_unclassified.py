"""Live unclassified catalogue; saved calculations are never rewritten here."""
from collections import defaultdict
from hashlib import sha256
import json
from statistics import median
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from organizations.models import Organization
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.parsers.regional_product_groups import get_prefixes_by_source, _normalized_url
from datasets.services.iprice_market_assortment import build_prefix_region_map, get_url_regions, split_regions
from . import iprice_domain_models as m

FIELDS = ('category', 'subcategory', 'subcategory_type', 'material', 'color', 'modification', 'article_number_analogs', 'item_type')
SOURCES = {'tara': m.TaraProductPrice, 'tt': m.TtProductPrice, 'ps': m.PsProductPrice}
WORKSPACE = IPriceWorkspace('select-market')


def groups():
    prefixes = get_prefixes_by_source(workspace=WORKSPACE)
    result = defaultdict(list)
    classified = m.ParserProductClassification.objects.filter(status='active').values('product_key')
    for source, model in SOURCES.items():
        latest = model.objects.filter(product_key=OuterRef('pk')).order_by('-date_add', '-pk')
        rows = m.ParserProductUrl.objects.filter(source=source, status='active').exclude(pk__in=classified).annotate(
            product_name=Subquery(latest.values('name')[:1]), product_image=Subquery(latest.values('image')[:1]))
        for row in rows.order_by('pk'):
            identity = _normalized_url(row.url, prefixes.get(source, set())) or str(row.pk)
            # Different commercial variants of the same URL must remain separate.
            result[(source, identity, row.additional_property or '')].append(row)
    return result


def token(rows):
    keys = sorted(row.pk for row in rows)
    records = list(m.ParserProductClassification.objects.filter(product_key__in=keys).order_by('product_key').values(
        'product_key', 'status', 'manual_edit', *FIELDS))
    return sha256(json.dumps([keys, records], sort_keys=True).encode()).hexdigest()


def catalogue(*, search='', source='', page=1):
    grouped = [rows for key, rows in groups().items() if (not source or key[0] == source) and (
        not search or any(search.casefold() in (row.product_name or '').casefold() or search.casefold() in (row.url or '').casefold() for row in rows))]
    grouped.sort(key=lambda rows: ((rows[0].product_name or rows[0].url or '').casefold(), rows[0].pk))
    from django.core.paginator import Paginator
    paginator = Paginator(grouped, 24)
    selected = paginator.get_page(page)
    keys = [row.pk for rows in selected for row in rows]
    prices = defaultdict(list)
    for model in SOURCES.values():
        latest = model.objects.filter(product_key=OuterRef('product_key')).order_by('-date_add', '-pk').annotate(day=TruncDate('date_add')).values('day')[:1]
        for price in model.objects.filter(product_key__in=keys).annotate(day=TruncDate('date_add')).filter(day=Subquery(latest)).order_by('pk'):
            prices[price.product_key].append(price)
    regions = build_prefix_region_map(workspace=WORKSPACE)
    cards = []
    for rows in selected:
        entries = defaultdict(list)
        for row in rows:
            labels = [region for value in get_url_regions(source=row.source, prefix=row.prefix, prefix_region_map=regions) for region in split_regions(value)] or ['—']
            observations = prices[row.pk]
            positive = [p.final_price for p in observations if p.final_price is not None and p.final_price > 0]
            price = median(positive) if positive else None
            day = timezone.localtime(observations[-1].date_add).date().isoformat() if observations else None
            for region in labels:
                entries[region].append({'price': price, 'date': day, 'url': row.url, 'product_key': row.pk})
        regional = []
        for region, values in sorted(entries.items()):
            positive = [v['price'] for v in values if v['price'] is not None]
            dates = sorted({v['date'] for v in values if v['price'] is not None and v['date']})
            regional.append({'region': region, 'price': median(positive) if positive else None, 'dates': dates,
                             'offers': values, 'urls': sorted({v['url'] for v in values if v['url']})})
        positive = [v['price'] for v in regional if v['price'] is not None]
        cards.append({'product_keys': sorted(row.pk for row in rows), 'revision': token(rows), 'source': rows[0].source,
            'name': next((row.product_name for row in rows if row.product_name), None),
            'image': next((row.product_image for row in rows if row.product_image), None), 'url': rows[0].url,
            'price': median(positive) if positive else None, 'regional_entries': regional,
            'dates': sorted({d for entry in regional for d in entry['dates']})})
    return {'results': cards, 'page': selected.number, 'pages': paginator.num_pages, 'count': paginator.count}


def refresh_manual_matches(keys):
    """Rebuild AUTO links for edited competitors using the spreadsheet matching rules."""
    from datasets.services.parsers.product_classification_match_loader import _colors_match
    active = m.ParserProductUrl.objects.filter(status='active')
    bases = list(m.ParserProductClassification.objects.filter(status='active', product_key__in=active.filter(source='base').values('pk')))
    competitors = m.ParserProductClassification.objects.filter(status='active', product_key__in=keys)
    manual = set(m.ParserProductMatch.objects.filter(match_type='manual', status='active', product_key_competitor__in=keys).values_list('product_key_base', 'product_key_competitor'))
    excluded = set(m.IPriceCompetitorSelectionOverride.objects.filter(selection_mode='exclude', product_key_competitor__in=keys).values_list('product_key_base', 'product_key_competitor'))
    m.ParserProductMatch.objects.filter(match_type='auto', product_key_competitor__in=keys).exclude(
        product_key_base__in=m.ParserProductUrl.objects.filter(source='base', status='inactive').values('pk')).update(status='inactive')
    def signature(row):
        return tuple((getattr(row, key) or '').strip().casefold() for key in ('article_number_analogs', 'item_type', 'category', 'subcategory', 'subcategory_type'))
    by_class = defaultdict(list)
    for base in bases:
        by_class[signature(base)].append(base)
    for competitor in competitors:
        for base in by_class[signature(competitor)]:
            pair = (base.product_key, competitor.product_key)
            if pair not in manual | excluded and _colors_match(base.color, competitor.color):
                m.ParserProductMatch.objects.update_or_create(product_key_base=pair[0], product_key_competitor=pair[1],
                    defaults={'match_type': 'auto', 'status': 'active'})


@transaction.atomic
def classify(*, keys, revision, values, reason, user, organization):
    Organization.objects.select_for_update().get(pk=organization.pk, code='select-market')
    rows = next((rows for rows in groups().values() if rows[0].pk in keys), None)
    if not rows or sorted(keys) != sorted(row.pk for row in rows) or revision != token(rows):
        raise ValueError('Состав или классификация товара изменились. Обновите список и повторите действие.')
    before = {str(row.product_key): {field: getattr(row, field) for field in FIELDS}
              for row in m.ParserProductClassification.objects.filter(product_key__in=keys)}
    for row in rows:
        m.ParserProductClassification.objects.update_or_create(product_key=row.pk, defaults={**values,
            'status': 'active', 'manual_edit': True, 'url': row.url, 'image': row.product_image, 'date_update': timezone.now()})
    refresh_manual_matches(keys)
    change = m.ClassificationChange.objects.create(product_keys=keys, before=before, after=values, reason=reason, changed_by=user)
    return change.pk
