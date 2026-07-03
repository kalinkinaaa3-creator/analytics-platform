from collections import defaultdict
from decimal import Decimal


def to_float(value):
    if value is None:
        return 0

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


def to_int(value):
    if value is None:
        return 0

    return int(value)


def month_key(value):
    if not value:
        return ""

    return value.strftime("%Y-%m")


def prepare_revenue_dashboard(
    rows: list[dict],
    filters: dict | None = None,
    filter_options: dict | None = None,
    last_update=None,
):
    filters = filters or {}
    filter_options = filter_options or {}

    total_revenue = Decimal("0")
    total_quantity = Decimal("0")
    total_weight = Decimal("0")

    shipments = set()
    clients = set()
    sku = set()

    new_sku = set()
    new_clients = set()

    by_month = defaultdict(
        lambda: {
            "revenue": Decimal("0"),
            "quantity": Decimal("0"),
            "weight_total": Decimal("0"),
            "shipments": set(),
            "clients": set(),
            "sku": set(),
            "new_sku": set(),
            "new_clients": set(),
        }
    )

    for row in rows:
        date_value = row.get("date")
        period = month_key(date_value)

        revenue = row.get("revenue") or Decimal("0")
        quantity = row.get("quantity") or Decimal("0")
        weight_total = row.get("weight_total") or Decimal("0")

        total_revenue += revenue
        total_quantity += quantity
        total_weight += weight_total

        type_doc = row.get("type_doc")
        partner_code = row.get("partner_code")
        partner = row.get("partner")
        nom_code = row.get("nom_code")
        nom = row.get("nom")

        client_key = partner_code if partner_code is not None else partner
        sku_key = nom_code if nom_code is not None else nom

        if type_doc:
            shipments.add(type_doc)

        if client_key:
            clients.add(client_key)

        if sku_key:
            sku.add(sku_key)

        if row.get("is_new_sku") and sku_key:
            new_sku.add(sku_key)

        if row.get("is_new_client") and client_key:
            new_clients.add(client_key)

        if period:
            by_month[period]["revenue"] += revenue
            by_month[period]["quantity"] += quantity
            by_month[period]["weight_total"] += weight_total

            if type_doc:
                by_month[period]["shipments"].add(type_doc)

            if client_key:
                by_month[period]["clients"].add(client_key)

            if sku_key:
                by_month[period]["sku"].add(sku_key)

            if row.get("is_new_sku") and sku_key:
                by_month[period]["new_sku"].add(sku_key)

            if row.get("is_new_client") and client_key:
                by_month[period]["new_clients"].add(client_key)

    periods = sorted(by_month.keys())

    charts = {
        "revenue": [],
        "quantity": [],
        "weight_total": [],
        "shipments": [],
        "clients": [],
        "sku": [],
        "new_sku": [],
        "new_clients": [],
    }

    for period in periods:
        item = by_month[period]

        charts["revenue"].append({
            "period": period,
            "value": to_float(item["revenue"]),
        })

        charts["quantity"].append({
            "period": period,
            "value": to_float(item["quantity"]),
        })

        charts["weight_total"].append({
            "period": period,
            "value": to_float(item["weight_total"]),
        })

        charts["shipments"].append({
            "period": period,
            "value": len(item["shipments"]),
        })

        charts["clients"].append({
            "period": period,
            "value": len(item["clients"]),
        })

        charts["sku"].append({
            "period": period,
            "value": len(item["sku"]),
        })

        charts["new_sku"].append({
            "period": period,
            "value": len(item["new_sku"]),
        })

        charts["new_clients"].append({
            "period": period,
            "value": len(item["new_clients"]),
        })

    return {
        "filters": filters,
        "filter_values": filter_options,
        "last_update": last_update.strftime("%Y-%m-%d %H:%M") if last_update else None,
        "kpi": {
            "revenue": to_float(total_revenue),
            "quantity": to_float(total_quantity),
            "weight_total": to_float(total_weight),
            "shipments": len(shipments),
            "clients": len(clients),
            "sku": len(sku),
            "new_sku": len(new_sku),
            "new_clients": len(new_clients),
        },
        "charts": charts,
    }