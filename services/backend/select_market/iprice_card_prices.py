"""Regional presentation of competitor cards; one median per region."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from statistics import median


def regional_card_prices(card):
    entries = card.get('regional_entries')
    if entries is None:
        entries = [
            {'region': region, 'price': variant.get('price'), 'url': variant.get('url')}
            for variant in card.get('variants', [])
            for region in (variant.get('regions') or ['—'])
        ]
    groups = defaultdict(list)
    names = {}
    for entry in entries:
        region = str(entry.get('region') or '—').strip()
        key = region.casefold()
        names[key] = region
        groups[key].append(entry)
    rows = []
    for key, values in sorted(groups.items()):
        prices = []
        for item in values:
            try:
                value = Decimal(str(item.get('price')))
                if value.is_finite() and value > 0:
                    prices.append(value)
            except (InvalidOperation, ValueError, TypeError):
                pass
        rows.append({'region': names[key], 'price': median(prices) if prices else None,
                     'urls': sorted({item['url'] for item in values if item.get('url')})})
    card['regional_entries'] = rows
    prices = [row['price'] for row in rows if row['price'] is not None]
    if rows:
        card['price'] = median(prices) if prices else None
    return card
