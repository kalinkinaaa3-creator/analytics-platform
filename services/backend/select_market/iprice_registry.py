"""Stable own-product identities. Call mutations under the organization lock."""
from django.db import transaction
from organizations.models import Organization
from .iprice_domain_models import BaseProductPrice, ParserProductUrl, ParserProductClassification
from .iprice_models import IPricePriceImport, NomenclaturePrice


def lock_registry():
    return Organization.objects.select_for_update().get(code='select-market', postgres_schema='select_market')


def bind_existing(*, offers=()):
    """Validate all claims before binding old IDs; never merge identities."""
    records = list(ParserProductUrl.objects.filter(source='base'))
    by_id = {row.pk: row for row in records}
    claims = {row.pk: {row.own_code} if row.own_code else set() for row in records}
    for key, code in BaseProductPrice.objects.values_list('product_key', 'code_1c').distinct():
        if code and key not in claims:
            raise ValueError(f'Реестр: данные сайта ссылаются на отсутствующий ID {key}. Требуется проверка.')
        if key in claims and code:
            claims[key].add(code)
    by_url = {}
    for row in records:
        if row.url:
            by_url.setdefault(row.url, []).append(row.pk)
    for offer in offers:
        for key in by_url.get(offer['url'], []):
            claims[key].add(offer['code_1c'])
    owners = {}
    for key, codes in claims.items():
        if len(codes) != 1:
            raise ValueError(f'Реестр: ID {key} имеет {len(codes)} кодов 1С. Требуется проверка, автоматическое объединение запрещено.')
        code = next(iter(codes))
        if not isinstance(code, str) or not code.strip() or code != code.strip() or len(code) > 160:
            raise ValueError(f'Реестр: некорректный текстовый код у ID {key}.')
        if code in owners:
            raise ValueError(f'Реестр: код {code} принадлежит ID {owners[code]} и {key}.')
        owners[code] = key
    changed = []
    for code, key in owners.items():
        row = by_id[key]
        if row.own_code is None:
            row.own_code = code
            # Existing active base URLs were maintained by the website loader.
            row.on_website = row.status == 'active' and row.is_loaded
            changed.append(row)
    ParserProductUrl.objects.bulk_update(changed, ['own_code', 'on_website'], batch_size=500)
    return len(changed)


def sync_price_membership():
    latest = IPricePriceImport.objects.order_by('-date').first()
    codes = set(NomenclaturePrice.objects.filter(batch=latest).values_list('code', flat=True)) if latest else set()
    known_codes = set(NomenclaturePrice.objects.values_list('code', flat=True))
    existing = set(ParserProductUrl.objects.filter(source='base').values_list('own_code', flat=True))
    ParserProductUrl.objects.bulk_create([
        ParserProductUrl(source='base', prefix='-', own_code=code, url=None, in_price=True)
        for code in sorted(known_codes - existing)
    ], batch_size=500)
    own = ParserProductUrl.objects.filter(source='base')
    own.update(in_price=False)
    own.filter(own_code__in=codes).update(in_price=True)
    refresh_status()


def refresh_status():
    from django.db.models import Q
    own = ParserProductUrl.objects.filter(source='base')
    own.filter(Q(in_price=True) | Q(on_website=True)).update(status='active')
    own.filter(in_price=False, on_website=False).update(status='inactive')


def sync_website(offers, *, complete=True):
    codes = [item['code_1c'] for item in offers]
    if len(set(codes)) != len(codes):
        raise ValueError('В XML повторяется код 1С. Загрузка отменена.')
    bind_existing(offers=offers)
    sync_price_membership()
    records = {row.own_code: row for row in ParserProductUrl.objects.filter(source='base')}
    created = updated = 0
    seen = set()
    for item in offers:
        row = records.get(item['code_1c'])
        # A URL cannot silently migrate to another product code.
        if ParserProductUrl.objects.filter(source='base', url=item['url']).exclude(own_code=item['code_1c']).exists():
            raise ValueError('URL уже связан с другим кодом 1С. Требуется проверка.')
        if row is None:
            row = ParserProductUrl(source='base', own_code=item['code_1c'])
            created += 1
        else:
            updated += 1
        row.url = item['url']
        row.prefix = '-'
        row.on_website = True
        row.status = 'active'
        row.last_error = None
        row.save()
        ParserProductClassification.objects.filter(product_key=row.pk).update(url=row.url)
        item['product_url_obj'] = row
        seen.add(row.pk)
    missing = ParserProductUrl.objects.filter(source='base', on_website=True).exclude(pk__in=seen)
    inactivated = missing.filter(in_price=False).count() if complete else 0
    if complete:
        missing.update(on_website=False, is_loaded=False)
    refresh_status()
    return {'created': created, 'updated': updated, 'inactivated': inactivated, 'active_ids': seen}


@transaction.atomic
def reconcile(*, apply=False):
    lock_registry()
    before = ParserProductUrl.objects.filter(source='base').count()
    bound = bind_existing()
    sync_price_membership()
    own = ParserProductUrl.objects.filter(source='base')
    report = {'bound': bound, 'created': own.count() - before, 'active': own.filter(status='active').count(),
              'price_only': own.filter(in_price=True, on_website=False).count(), 'inactive': own.filter(status='inactive').count()}
    if not apply:
        transaction.set_rollback(True)
    return report
