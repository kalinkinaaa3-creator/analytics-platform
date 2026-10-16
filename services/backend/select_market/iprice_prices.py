"""Validate an entire XLSX before atomically publishing its dated price list."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from django.db import transaction
from openpyxl import load_workbook

from organizations.models import Organization
from .iprice_models import IPricePriceImport, NomenclaturePrice

PRICE_FIELDS = ("large", "small", "retail", "medium")
COLUMNS = ("Код", "Регион", "Номенклатура", "Группа", "Группа", "Группа", "Группа",
           "Крупный опт", "Мелкий опт", "Розница", "Средний опт")


def whole_rubles(value):
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def price_with_vat(net):
    return whole_rubles(Decimal(net) * Decimal("1.22"))


class PriceImportError(ValueError):
    pass


def parse_price_file(content, *, price_date):
    try:
        day = price_date.date() if isinstance(price_date, datetime) else price_date if isinstance(price_date, date) else date.fromisoformat(str(price_date))
    except (ValueError, TypeError):
        raise PriceImportError("Выберите дату полного прайса.") from None
    if len(content) > 10 * 1024 * 1024:
        raise PriceImportError("Размер файла не должен превышать 10 МБ.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise PriceImportError("Распакованный XLSX превышает 100 МБ.")
    except BadZipFile as exc:
        raise PriceImportError("Не удалось прочитать XLSX.") from exc
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=False)
    except Exception as exc:
        raise PriceImportError("Не удалось прочитать XLSX.") from exc
    try:
        if len(book.worksheets) != 1:
            raise PriceImportError("В файле должен быть один лист с полным прайсом.")
        rows = iter(book.active.iter_rows(values_only=True))
        header = tuple(str(v).strip() if v is not None else "" for v in next(rows, ()))
        if header != COLUMNS:
            raise PriceImportError("Ожидаются столбцы: " + ", ".join(COLUMNS))
        result, keys, dates = [], set(), set()
        for number, values in enumerate(rows, 2):
            if number > 100001:
                raise PriceImportError("В прайсе допускается не более 100 000 строк.")
            if all(v is None or v == "" for v in values):
                continue
            try:
                if any(isinstance(value, str) and value.startswith("=") for value in values):
                    raise ValueError("формулы не допускаются, вставьте значения")
                row = dict(zip(("code", "shipp_region", "nom"), values[:3]))
                row["date"] = day
                groups = [str(value).strip() for value in reversed(values[3:7]) if value is not None and str(value).strip()]
                if any(len(value) > 255 for value in groups):
                    raise ValueError("слишком длинное наименование группы")
                row.update({f"group_{index + 1}": groups[index] if index < len(groups) else "" for index in range(4)})
                row.update(zip(PRICE_FIELDS, values[7:11]))
                for field in ("code", "shipp_region", "nom"):
                    value = row[field]
                    if field == "code" and not isinstance(value, str):
                        raise ValueError("код должен быть текстовой ячейкой Excel")
                    value = "" if value is None else str(value).strip()
                    if value.startswith("=") or (field != "nom" and not value):
                        raise ValueError(f"некорректное поле {field}")
                    if len(value) > (160 if field == "code" else 255):
                        raise ValueError(f"слишком длинное поле {field}")
                    row[field] = value
                for field in PRICE_FIELDS:
                    value = row[field]
                    if value is None or value == "":
                        row[field] = None
                        row[field + "_gross"] = None
                        continue
                    amount = Decimal(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
                    if not amount.is_finite() or amount < 0 or amount >= Decimal("1e14") or amount != amount.quantize(Decimal("0.0001")):
                        raise ValueError(f"некорректная цена {field}")
                    row[field + "_gross"] = amount
                    row[field] = whole_rubles(amount / Decimal("1.22"))
                key = (row["shipp_region"].casefold(), row["code"])
                if key in keys:
                    raise ValueError("повтор кода в одном регионе")
                keys.add(key)
                dates.add(row["date"])
                result.append(row)
            except (ValueError, TypeError, InvalidOperation, KeyError) as exc:
                raise PriceImportError(f"Строка {number}: {exc}") from exc
        if not result or len(dates) != 1:
            raise PriceImportError("Нужен непустой полный прайс за одну дату.")
        return result
    finally:
        book.close()


def import_price_file(content, *, filename, user, organization, price_date):
    if organization.code != "select-market" or organization.postgres_schema != "select_market":
        raise PriceImportError("Загрузка разрешена только для Селект Маркета.")
    rows = parse_price_file(content, price_date=price_date)
    digest = sha256(content).hexdigest()
    with transaction.atomic():
        # Serializes even the first import, when no dated batch exists yet.
        Organization.objects.select_for_update().get(pk=organization.pk)
        batch = IPricePriceImport.objects.filter(date=rows[0]["date"]).first()
        if batch and batch.checksum == digest:
            return batch
        revision = batch.revision + 1 if batch else 1
        batch, _ = IPricePriceImport.objects.update_or_create(date=rows[0]["date"], defaults={
            "filename": filename[:255], "checksum": digest, "rows": len(rows),
            "revision": revision, "user": user,
        })
        NomenclaturePrice.objects.filter(date=batch.date).delete()
        NomenclaturePrice.objects.bulk_create([NomenclaturePrice(batch=batch, **row) for row in rows], batch_size=500)
    return batch


def prices_as_of(calculation_date):
    """A missing SKU in the selected complete list never falls back individually."""
    batch = IPricePriceImport.objects.filter(date__lte=calculation_date).order_by("-date").first()
    return NomenclaturePrice.objects.filter(batch=batch) if batch else NomenclaturePrice.objects.none()
