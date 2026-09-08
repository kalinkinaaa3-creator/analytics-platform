"""Weekly revenue from the same ClickHouse facts as the Revenue dashboard."""
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256

from analytics.clickhouse.client import get_clickhouse_client


OTHER = "Прочие"


def direction_order(name):
    value = name.strip().casefold()
    if value == OTHER.casefold():
        return (99, value)
    for index, roots in enumerate((('стратег',), ('рег',), ('апк',), ('тко',), ('логист', 'спп'))):
        if any(root in value for root in roots):
            return (index, value)
    return (98, value)


def add_revenue(rows, filters, client=None):
    client = client or get_clickhouse_client()
    # Fetch names independently of the selected weeks, preserving zero-value columns.
    names = {name or OTHER for name, in client.execute(
        "SELECT DISTINCT direction FROM default.revenue_sales"
    )}
    facts = client.execute("""
        SELECT toStartOfWeek(date, 1), direction, sum(revenue)
        FROM default.revenue_sales
        WHERE date >= %(start)s AND date < %(end)s
        GROUP BY toStartOfWeek(date, 1), direction
    """, {"start": filters["week_from"], "end": filters["week_to"] + timedelta(days=7)})
    names.update(name or OTHER for _, name, _ in facts)
    directions = [{"key": "revenue_1c_" + sha256(name.encode()).hexdigest(),
                   "name": name, "is_other": name.strip().casefold() == OTHER.casefold()}
                  for name in sorted(names, key=direction_order)]
    keys = {item["name"]: item["key"] for item in directions}
    weekly = {}
    for week, name, amount in facts:
        values = weekly.setdefault(week.isoformat(), {})
        key = keys[name or OTHER]
        values[key] = values.get(key, Decimal(0)) + Decimal(str(amount or 0))
    for row in rows:
        values = weekly.get(row["week_start"], {})
        row["revenue_1c_total"] = float(sum(values.values(), Decimal(0)))
        row.update({item["key"]: float(values.get(item["key"], 0)) for item in directions})
    return directions
