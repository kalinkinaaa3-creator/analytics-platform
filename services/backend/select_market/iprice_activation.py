"""Validation inside the shared activation transaction and workspace lock."""
from django.db.models import Prefetch


def validate_activation(snapshot):
    from datasets.services.iprice_snapshot_builder import IPriceSnapshotBuildError
    from datasets.services.iprice_snapshot_export import get_effective_prices
    from .iprice_domain_models import IPriceSnapshotApproval, IPriceSnapshotRegion

    if IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=snapshot).exclude(historical_variant='').exists():
        raise IPriceSnapshotBuildError('Это историческая версия с маршрутами. Создайте новый расчёт для утверждения.')

    if snapshot.products.exclude(calculation_status__in=['success', 'warning']).exists():
        raise IPriceSnapshotBuildError('В расчёте есть товары с ошибками.')
    if snapshot.products.exclude(error_codes=[]).exists() or snapshot.products.filter(regions__isnull=True).exists():
        raise IPriceSnapshotBuildError('В расчёте есть товары с ошибками или без региональных цен.')
    rows = IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=snapshot).prefetch_related(
        Prefetch('approvals', queryset=IPriceSnapshotApproval.objects.filter(is_current=True)
                 .select_related('approved_by').order_by('-revision', '-id'),
                 to_attr='prefetched_current_approvals'))
    found = False
    for row in rows.iterator(chunk_size=500):
        found = True
        if 'REAPPROVAL_REQUIRED' in row.warning_codes:
            raise IPriceSnapshotBuildError('После изменения параметров требуется повторное согласование цен.')
        if row.calculation_status not in ('success', 'warning') or row.error_codes:
            raise IPriceSnapshotBuildError('В расчёте есть региональные строки с ошибками.')
        prices = get_effective_prices(row)
        if any(prices[key] is None or prices[key] <= 0
               for key in ('rrp', 'small', 'medium', 'large')):
            raise IPriceSnapshotBuildError('Не все итоговые цены заполнены положительными значениями.')
        from .iprice_regional_calculation import prices_meet_margin
        if not prices_meet_margin(row, [prices[key] for key in ('rrp', 'small', 'medium', 'large')]):
            raise IPriceSnapshotBuildError('Итоговые цены нарушают минимальную маржу. Пересчитайте или согласуйте цены.')
    if not found:
        raise IPriceSnapshotBuildError('В расчёте отсутствуют региональные строки.')
