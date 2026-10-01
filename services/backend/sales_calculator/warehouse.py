import json
import logging
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.utils import timezone

from analytics.clickhouse.client import get_clickhouse_client
from .configuration import CHARACTERISTICS, LOGISTICS
from .properties import SOURCE_NAMES, VALUE_LABELS, normalized

logger = logging.getLogger("sales_calculator")
TABLE = "default.sales_calculator_product"
TEXT_FIELDS = ("url", "color", "image", "name", "name_1c", "price_list", "nom_view", "nom_category", "nom_group", "nom_cn_fea", "sam")
JSON_FIELDS = ("characteristics", "logistics", "stocks")
COLUMNS = ", ".join(("product_key", "code", "region", "calculation_date", "retail", "small", "medium", "large", "distr", "distr_1", *TEXT_FIELDS, "quantity_eurotruck", *JSON_FIELDS, "payload"))


def ensure_table(client):
    client.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE} (
        product_key UInt64, code Int64, region String, calculation_date Date,
        retail Nullable(Decimal(18,4)), small Nullable(Decimal(18,4)),
        medium Nullable(Decimal(18,4)), large Nullable(Decimal(18,4)),
        distr Nullable(Decimal(18,4)), distr_1 Nullable(Decimal(18,4)),
        {', '.join(f'{field} String' for field in TEXT_FIELDS)},
        quantity_eurotruck Nullable(Decimal(18,4)),
        characteristics String, logistics String, stocks String, payload String
    ) ENGINE=MergeTree ORDER BY (region, code, product_key)""")


def _number(value):
    try:
        result = Decimal(str(value).replace(" ", "").replace("\xa0", "").replace(",", "."))
        return str(result) if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def decorate(row, properties):
    normalized_properties = {normalized(key): value for key, value in properties.items()}
    def prop(*names):
        for name in names:
            value = properties[name] if name in properties else normalized_properties.get(normalized(name))
            if value is not None and str(value).strip() not in ("", "-", "—"):
                return str(value).strip()
        return None
    dimensions = [prop("Длина (Глубина), мм", "Длина, мм"), prop("Ширина, мм"), prop("Высота, мм")]
    chars = {
        "dimensions": " × ".join(dimensions) if all(dimensions) else None,
        "color": row.get("color"), "bottom": prop("Тип дна"), "walls": prop("Тип стенок"),
        "perforation": "перфорированные" if (prop("Перфорация стенок") or "").casefold() == "да" else None,
        "lid": prop("Тип крышки"), "equipment": prop("Комплектация", "Комплектация с пояснениями"),
        "loading": prop("Максимальная загрузка, кг"), "load": prop("Максимальная нагрузка, кг"),
        "dynamic_load": prop("Максимальная динамическая нагрузка, кг"),
        "shelf_load": prop("Максимальная нагрузка на полку, кг"),
        "volume": prop("Объём, л", "Объем, л"), "weight": prop("Вес, кг"),
    }
    for key, source in SOURCE_NAMES.items():
        value = prop(source)
        chars[key] = VALUE_LABELS[key].get(normalized(value)) if key in VALUE_LABELS else value
    packing = prop("Способ сложения (коробка)")
    logistics = {
        "pallet": prop("Количество на паллетоместе (для прайса)", "Количество на паллете, шт."), "truck": row.get("quantity_eurotruck"),
        "truck82_no_pallet": prop("Количество в еврофуре 82 м3, шт. (отгрузка без паллеты)"),
        "truck82": prop("Количество в еврофуре 82 м3, шт.", "Количество в еврофуре 82 м³, шт."),
        "pallet_size": prop("Размер паллето-места, мм"),
        "packing": f"по {packing} шт./короб" if packing and _number(packing) else packing,
        "tnved": row.get("nom_cn_fea"),
    }
    row["characteristics"] = {k: str(v) for k, v in chars.items() if v not in (None, "", "-")}
    row["logistics"] = {k: str(v) for k, v in logistics.items() if v not in (None, "", "-")}
    row["weight_value"] = _number(chars["weight"])
    row["pallet_value"] = _number(logistics["pallet"])
    row["sam"] = prop("Статус ассортиментной матрицы", "Статус ассортиментной матрицы (САМ)", "САМ") or ""
    row["our_offers"] = prop("Наши предложения") or ""
    row["material"] = prop("Материал") or ""
    row["price_list_name"] = prop("Номенклатура прайс-листа") or row.get("name")
    return row


def build_rows(day, stock_available):
    # PostgreSQL provides a single consistent source snapshot; no historical price fallback.
    with connection.cursor() as cursor:
        cursor.execute("""
            WITH b AS (
                SELECT DISTINCT ON (product_key) * FROM base_product_price
                ORDER BY product_key, date_add DESC, id DESC
            ), n AS (
                SELECT DISTINCT ON (nom_code) * FROM nomenclature ORDER BY nom_code, date_add DESC, id DESC
            ), p AS (
                SELECT DISTINCT ON (code, shipp_region) * FROM public.nomenclature_price
                WHERE date=%s AND NULLIF(BTRIM(shipp_region),'') IS NOT NULL
                ORDER BY code, shipp_region, id DESC
            )
            SELECT b.product_key, b.code_1c AS code, p.shipp_region AS region,
                p.retail, p.small, p.medium, p.large, p.distr, p.distr_1, p.price_list AS price_list,
                b.url, b.color, b.image, b.name, n.nom AS name_1c,
                n.nom_view, n.nom_category, n.nom_group, n.nom_cn_fea, n.quantity_eurotruck
            FROM b JOIN p ON p.code=b.code_1c LEFT JOIN n ON n.nom_code=b.code_1c
        """, [day])
        keys = [d[0] for d in cursor.description]
        rows = [dict(zip(keys, values)) for values in cursor.fetchall()]
        cursor.execute("""SELECT DISTINCT ON (product_key, properties) product_key, properties, value
            FROM parser_product_property WHERE source='base'
            ORDER BY product_key, properties, date_add DESC, id DESC""")
        properties = {}
        for key, name, value in cursor.fetchall():
            properties.setdefault(key, {})[name] = value
        stocks = {}
        if stock_available:
            cursor.execute("""SELECT nom_code, warehouse, SUM(quantity) FROM nomenclature_stock
                              WHERE date=%s GROUP BY nom_code, warehouse""", [day])
            for code, warehouse, quantity in cursor.fetchall():
                if warehouse:
                    stocks.setdefault(code, {})[warehouse] = quantity
    for row in rows:
        decorate(row, properties.get(row["product_key"], {}))
        row["calculation_date"] = day.isoformat()
        row["stocks"] = stocks.get(row["code"], {}) if stock_available else None
    return rows


def publish(day, stock_available):
    from django.db import transaction
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        rows = build_rows(day, stock_available)
    client = get_clickhouse_client()
    ensure_table(client)
    shadow = TABLE + "_build_" + uuid4().hex
    client.execute(f"CREATE TABLE {shadow} AS {TABLE}")
    try:
        for offset in range(0, len(rows), 1000):
            values = [(r["product_key"], r["code"], r["region"], day,
                       *[r[t] for t in ("retail", "small", "medium", "large", "distr", "distr_1")],
                       *[str(r.get(field) or "") for field in TEXT_FIELDS],
                       Decimal(_number(r.get("quantity_eurotruck"))) if _number(r.get("quantity_eurotruck")) is not None else None,
                       *[json.dumps(r.get(field), cls=DjangoJSONEncoder, ensure_ascii=False) for field in JSON_FIELDS],
                       json.dumps(r, cls=DjangoJSONEncoder, ensure_ascii=False)) for r in rows[offset:offset+1000]]
            client.execute(f"INSERT INTO {shadow} ({COLUMNS}) VALUES", values)
        # Atomic database (the project's default): readers see old or complete new data.
        client.execute(f"EXCHANGE TABLES {TABLE} AND {shadow}")
    finally:
        try:
            client.execute(f"DROP TABLE IF EXISTS {shadow}")
        except Exception:
            # Cleanup cannot undo a completed atomic publication or hide its original error.
            logger.exception("Could not remove commercial price staging table %s", shadow)
    return len(rows)


def read_products(region=None):
    client = get_clickhouse_client()
    ensure_table(client)
    sql = f"SELECT payload FROM {TABLE}"
    params = {}
    if region is not None:
        sql += " WHERE region=%(region)s"
        params["region"] = region
    sql += " ORDER BY code, product_key"
    return [json.loads(payload) for (payload,) in client.execute(sql, params)]
