import hashlib
import io
import logging
import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import requests
from django.conf import settings

from .configuration import CHARACTERISTICS, LOGISTICS, FULL_COLUMNS, SIMPLE_COLUMNS, PRICE_LABELS

logger = logging.getLogger("sales_calculator")
PRICE_COLUMNS = {"unit_net", "unit_gross", *[f"{tier}_{tax}" for tier in PRICE_LABELS for tax in ("net", "gross")]}
NUMERIC_COLUMNS = PRICE_COLUMNS | {"quantity", "sum_net", "sum_gross", "code", "row_number"}


def price_text(value):
    value = Decimal(str(value))
    digits = max(0, -value.normalize().as_tuple().exponent)
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def image_bytes(url):
    # Only server-selected product images from the source site's public HTTPS host.
    try:
        parsed = urlsplit(url or "")
        valid = parsed.scheme == "https" and parsed.hostname in ("iplast.com", "www.iplast.com") and parsed.port in (None, 443) and not parsed.username
    except ValueError:
        return None
    if not valid:
        return None
    try:
        folder = Path(settings.MEDIA_ROOT) / "sales-calculator-images"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (hashlib.sha256(url.encode()).hexdigest() + ".png")
        if path.exists():
            return path.read_bytes()
        from PIL import Image
        with requests.get(url, timeout=(5, 10), stream=True, allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200:
                return None
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 5 * 1024 * 1024:
                    return None
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 20000000:
                return None
            image.thumbnail((300, 220))
            output = io.BytesIO()
            image.convert("RGBA").save(output, format="PNG")
        result = output.getvalue()
        temp = path.with_name(path.name + f".{os.getpid()}.tmp")
        temp.write_bytes(result)
        temp.replace(path)
        return result
    except Exception:
        logger.warning("Product image could not be embedded")
        return None


def comparison_column(row, key):
    return bool(row.get("_warehouse_prices")) and key.endswith(("_net", "_gross"))


def display(row, key, config):
    if comparison_column(row, key):
        return "\n".join(
            f"{region}: {price_text(values[key]) if values.get(key) is not None else '—'}"
            for region, values in row["_warehouse_prices"]
        )
    if key == "name":
        return row.get("price_list_name") or row.get("name") or ""
    if key == "code":
        return str(row.get("code") or "").zfill(11) if row.get("code") is not None else ""
    if key in ("characteristics", "logistics"):
        labels = CHARACTERISTICS if key == "characteristics" else LOGISTICS
        return "\n".join(f"{labels[k]}: {row.get(key, {}).get(k)}" for k in config[key] if row.get(key, {}).get(k) not in (None, ""))
    if key == "price_type":
        return PRICE_LABELS[row[key]]
    if key == "url":
        return "Посмотреть" if row.get(key) else ""
    value = row.get(key)
    return "" if value is None else value


def export_document(result, config, mode, kind):
    labels = dict(FULL_COLUMNS if mode == "full" else SIMPLE_COLUMNS)
    if mode == "simple":
        bounds = [price_text(value) for value in [0, *config["thresholds"]]]
        for index, (tier, label) in enumerate(PRICE_LABELS.items()):
            band = f"{bounds[index]}–{bounds[index + 1]} руб." if index < 3 else f"свыше {bounds[index]} руб."
            for tax in ("net", "gross"):
                labels[f"{tier}_{tax}"] = f"{label} руб. {'без НДС' if tax == 'net' else 'с НДС'}\n({band})"
    columns = config[mode + "_columns"]
    if not columns:
        raise ValueError("Выберите столбцы для выгрузки")
    columns = ["row_number", *columns]
    labels["row_number"] = "№"
    result = {**result, "rows": [{**row, "row_number": index} for index, row in enumerate(result["rows"], 1)]}
    if result.get("warehouses"):
        warehouses = [(warehouse["region"], {str(row["product_key"]): row for row in warehouse["rows"]})
                      for warehouse in result["warehouses"]]
        for row in result["rows"]:
            row["_warehouse_prices"] = [(region, products.get(str(row["product_key"]), {})) for region, products in warehouses]
    # Shared columns and data are used by both formats.
    from concurrent.futures import ThreadPoolExecutor
    urls = list(dict.fromkeys(r.get("image") for r in result["rows"] if r.get("image"))) if "image" in columns else []
    with ThreadPoolExecutor(max_workers=4) as executor:
        images = dict(zip(urls, executor.map(image_bytes, urls)))
    from .export_layout import xlsx, pdf
    return (xlsx if kind == "xlsx" else pdf)(result, config, mode, labels, columns, images)
