"""Current manual decisions and the latest historical decision for selected price rows."""
from hashlib import sha256

from .iprice_domain_models import IPriceSnapshotApproval


def manual_price_review(rows):
    rows = list(rows)
    codes = {row.snapshot_product.code_1c for row in rows}
    approvals = IPriceSnapshotApproval.objects.filter(snapshot_region__snapshot_product__code_1c__in=codes).select_related(
        'snapshot_region__snapshot_product__snapshot', 'approved_by').order_by('-approved_at', '-pk')
    latest, current = {}, {}
    selected_ids = {row.pk for row in rows}
    for approval in approvals:
        region = approval.snapshot_region
        pair = (region.snapshot_product.code_1c, region.sale_region.casefold())
        latest.setdefault(pair, approval)
        if region.pk in selected_ids and approval.is_current:
            current.setdefault(region.pk, approval)

    def describe(approval):
        return {'id': approval.pk, 'price': str(approval.approved_rrp),
                'at': approval.approved_at.isoformat(), 'user': approval.approved_by.get_username() if approval.approved_by else None,
                'snapshot_id': approval.snapshot_region.snapshot_product.snapshot_id,
                'version': approval.snapshot_region.snapshot_product.snapshot.version_number}

    items = []
    for row in rows:
        last = latest.get((row.snapshot_product.code_1c, row.sale_region.casefold()))
        active = current.get(row.pk)
        if last is None:
            continue
        items.append({'row_id': row.pk, 'product_id': row.snapshot_product_id, 'code_1c': row.snapshot_product.code_1c,
                      'name': row.snapshot_product.nom, 'region': row.sale_region,
                      'current': describe(active) if active else None, 'latest': describe(last)})
    items.sort(key=lambda item: (item['code_1c'], item['region'], item['row_id']))
    signature = sha256(';'.join(f"{item['row_id']}:{(item['current'] or {}).get('id', '')}:{item['latest']['id']}"
                                for item in items).encode()).hexdigest()
    return items, signature
