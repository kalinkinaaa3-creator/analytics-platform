from __future__ import annotations

import hashlib
from decimal import Decimal
from zipfile import BadZipFile

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from datasets.models import (
    AnalyticsProductAnalysisResult,
    AnalyticsProductClassificationApplication,
    AnalyticsProductDirectoryLoad,
    AnalyticsProductMatchCandidate,
    AnalyticsProductProcessingRun,
    ParserProductClassification,
    ParserProductMatch,
    IPriceCompetitorSelectionOverride,
)
from datasets.services.parsers.analytics_product_normalization import normalize_text
from datasets.services.parsers.analytics_product_processor import (
    DirectoryRuntime,
    _apply_matching,
    build_modification,
)
from datasets.services.parsers.analytics_product_lock import (
    analytics_product_operation_lock,
)
from datasets.services.parsers.product_url_export import (
    WILDCARD_COLOR_LABEL,
    WILDCARD_COLOR_VALUE,
)
from datasets.services.parsers.product_match_loader import (
    build_competitor_url_groups,
    get_prefixes_by_source,
)


class AnalyticsProductClassificationApplyError(ValueError):
    pass


REQUIRED_HEADERS = {
    "calculation_version", "include", "product_key", "source", "category",
    "subcategory", "subcategory_type", "material", "color", "modification",
    "item_type",
}
TRUE_VALUES = {"1", "yes", "true", "да", "включить"}
FALSE_VALUES = {"0", "no", "false", "нет", "исключить"}
MAX_CLASSIFICATION_FILE_SIZE = 50 * 1024 * 1024
MAX_CLASSIFICATION_ROWS = 250_000


def expand_eligible_match_pairs(
    *,
    eligible_pairs,
    included_keys,
    competitor_groups,
    competitor_group_key_by_product,
):
    """Expand a weighted pair to every included regional URL copy."""
    included_keys = set(included_keys)
    expanded = set()
    for base_key, competitor_key in eligible_pairs:
        if base_key not in included_keys or competitor_key not in included_keys:
            continue
        group_key = competitor_group_key_by_product.get(competitor_key)
        regional_keys = (
            competitor_groups.get(group_key, set())
            if group_key is not None
            else {competitor_key}
        )
        regional_keys = set(regional_keys) | {competitor_key}
        for regional_key in regional_keys & included_keys:
            expanded.add((base_key, regional_key))
    return sorted(expanded)


def _text(value):
    return "" if value is None else str(value).strip()


def _integer(value, *, location):
    try:
        return int(Decimal(_text(value)))
    except Exception as exc:
        raise AnalyticsProductClassificationApplyError(
            f"{location}: ожидается целое число"
        ) from exc


def _include(value, *, location):
    normalized = normalize_text(value)
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise AnalyticsProductClassificationApplyError(
        f"{location}: include должен быть Да или Нет"
    )


def _checksum(file_obj):
    digest = hashlib.sha256()
    total = 0
    file_obj.seek(0)
    while True:
        chunk = file_obj.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_CLASSIFICATION_FILE_SIZE:
            raise AnalyticsProductClassificationApplyError(
                "Файл классификации превышает допустимый размер 50 МБ"
            )
        digest.update(chunk)
    file_obj.seek(0)
    return digest.hexdigest()


def _read_rows(file_obj):
    file_obj.seek(0)
    try:
        workbook = load_workbook(file_obj, read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, ValueError) as exc:
        raise AnalyticsProductClassificationApplyError(
            f"Не удалось прочитать файл классификации: {exc}"
        ) from exc
    try:
        worksheet = None
        for candidate in workbook.worksheets:
            raw_headers = next(
                candidate.iter_rows(min_row=1, max_row=1, values_only=True),
                (),
            )
            candidate_headers = {_text(value) for value in raw_headers}
            if REQUIRED_HEADERS <= candidate_headers:
                worksheet = candidate
                break
        if worksheet is None:
            raise AnalyticsProductClassificationApplyError(
                "В файле не найден лист классификации с обязательными столбцами: "
                + ", ".join(sorted(REQUIRED_HEADERS))
            )
        iterator = worksheet.iter_rows(values_only=True)
        try:
            raw_headers = next(iterator)
        except StopIteration as exc:
            raise AnalyticsProductClassificationApplyError(
                "Файл классификации пуст"
            ) from exc
        headers = [_text(value) for value in raw_headers]
        duplicate_headers = sorted({
            header for header in headers
            if header and headers.count(header) > 1
        })
        if duplicate_headers:
            raise AnalyticsProductClassificationApplyError(
                "Повторяются заголовки: " + ", ".join(duplicate_headers)
            )
        missing = sorted(REQUIRED_HEADERS - set(headers))
        if missing:
            raise AnalyticsProductClassificationApplyError(
                "Отсутствуют столбцы классификации: " + ", ".join(missing)
            )
        result = []
        for row_number, values in enumerate(iterator, 2):
            if row_number > MAX_CLASSIFICATION_ROWS + 1:
                raise AnalyticsProductClassificationApplyError(
                    f"Лист классификации содержит больше "
                    f"{MAX_CLASSIFICATION_ROWS} строк"
                )
            row = dict(zip(headers, values))
            if not any(value not in (None, "") for value in values):
                continue
            row["_row_number"] = row_number
            result.append(row)
        return result
    finally:
        workbook.close()


def _validate_rows(rows):
    if not rows:
        raise AnalyticsProductClassificationApplyError(
            "Лист классификации не содержит товаров"
        )
    versions = {
        _integer(row.get("calculation_version"), location=f"строка {row['_row_number']}")
        for row in rows
    }
    if len(versions) != 1:
        raise AnalyticsProductClassificationApplyError(
            "Все строки должны относиться к одной calculation_version"
        )
    run_id = versions.pop()
    try:
        run = AnalyticsProductProcessingRun.objects.get(
            pk=run_id, status=AnalyticsProductProcessingRun.STATUS_SUCCESS
        )
    except AnalyticsProductProcessingRun.DoesNotExist as exc:
        raise AnalyticsProductClassificationApplyError(
            f"Успешный расчёт Product Control #{run_id} не найден"
        ) from exc
    latest_directory = AnalyticsProductDirectoryLoad.objects.filter(
        status=AnalyticsProductDirectoryLoad.STATUS_SUCCESS
    ).order_by("-date_add", "-id").first()
    if latest_directory is None or run.directory_load_id != latest_directory.id:
        raise AnalyticsProductClassificationApplyError(
            f"Расчёт #{run_id} создан не по текущей версии directory. "
            "Выгрузите и проверьте актуальный результат Product Control."
        )

    expected = {
        row.product_key: row
        for row in AnalyticsProductAnalysisResult.objects.filter(run=run).iterator(
            chunk_size=500
        )
    }
    prepared = {}
    errors = []
    runtime = DirectoryRuntime()
    for raw in rows:
        number = raw["_row_number"]
        try:
            product_key = _integer(raw.get("product_key"), location=f"строка {number}")
        except AnalyticsProductClassificationApplyError as exc:
            errors.append(str(exc))
            continue
        if product_key in prepared:
            errors.append(f"строка {number}: повтор product_key={product_key}")
            continue
        original = expected.get(product_key)
        if original is None:
            errors.append(f"строка {number}: product_key={product_key} отсутствует в расчёте #{run_id}")
            continue
        source = _text(raw.get("source"))
        if source != original.source:
            errors.append(
                f"строка {number}: source={source!r} не соответствует {original.source!r}"
            )
        try:
            included = _include(raw.get("include"), location=f"строка {number}")
        except AnalyticsProductClassificationApplyError as exc:
            errors.append(str(exc))
            included = False
        values = {
            name: _text(raw.get(name))
            for name in (
                "category", "subcategory", "subcategory_type", "material", "color",
                "modification", "item_type",
            )
        }
        if included:
            missing = [
                name for name in (
                    "category", "subcategory", "subcategory_type", "material",
                    "color", "item_type",
                )
                if not values[name]
            ]
            if missing:
                errors.append(
                    f"строка {number}: для include=Да не заполнены {', '.join(missing)}"
                )
            if values["item_type"] not in {"product", "component"}:
                errors.append(f"строка {number}: item_type должен быть product или component")
            decision = type("Decision", (), values)()
            if runtime.profile(runtime.matching_profiles, decision) is None:
                errors.append(
                    f"строка {number}: для указанной классификации нет matching_score"
                )
        prepared[product_key] = {
            "included": included, "original": original, **values,
        }

    missing_keys = sorted(set(expected) - set(prepared))
    if missing_keys:
        preview = ", ".join(str(value) for value in missing_keys[:20])
        suffix = "…" if len(missing_keys) > 20 else ""
        errors.append(
            f"В файле отсутствуют {len(missing_keys)} товаров расчёта #{run_id}: {preview}{suffix}"
        )
    if errors:
        raise AnalyticsProductClassificationApplyError("\n".join(errors[:100]))
    return run, prepared


def _apply_analytics_product_classification_locked(
    file_obj, *, filename="", user=None
):
    checksum = _checksum(file_obj)
    rows = _read_rows(file_obj)
    run, prepared = _validate_rows(rows)
    now = timezone.now()
    runtime = DirectoryRuntime()

    with transaction.atomic():
        analysis_updates = []
        included_keys = set()
        for product_key, values in prepared.items():
            row = values["original"]
            if values["included"]:
                included_keys.add(product_key)
                row.item_type = values["item_type"]
                row.category = values["category"]
                row.subcategory = values["subcategory"]
                row.subcategory_type = values["subcategory_type"]
                properties = dict(row.normalized_properties or {})
                if values["material"]:
                    properties["material"] = values["material"]
                if values["color"]:
                    properties["color"] = (
                        WILDCARD_COLOR_VALUE
                        if normalize_text(values["color"])
                        == normalize_text(WILDCARD_COLOR_LABEL)
                        else values["color"]
                    )
                row.normalized_properties = properties
                decision = type("Decision", (), values)()
                modification, modification_code, modification_reason = (
                    build_modification(runtime, properties, decision)
                )
                row.modification = modification
                row.modification_code = modification_code
                row.classification_status = "classified"
                row.control_reasons = (
                    [modification_reason] if modification_reason else []
                )
            else:
                row.classification_status = "excluded"
                row.match_status = ""
            analysis_updates.append(row)
        AnalyticsProductAnalysisResult.objects.bulk_update(
            analysis_updates,
            fields=(
                "item_type", "category", "subcategory", "subcategory_type",
                "modification", "modification_code", "normalized_properties",
                "classification_status", "match_status", "control_reasons",
            ),
            batch_size=200,
        )

        application = AnalyticsProductClassificationApplication.objects.create(
            run=run,
            uploaded_by=user if getattr(user, "is_authenticated", False) else None,
            filename=filename,
            checksum=checksum,
        )
        eligible_matches = _apply_matching(
            run, runtime, application=application
        )

        ParserProductClassification.objects.filter(status="active").update(
            status="inactive", date_update=now
        )
        existing_classifications = {
            row.product_key: row
            for row in ParserProductClassification.objects.filter(
                product_key__in=included_keys
            ).iterator(chunk_size=500)
        }
        to_create = []
        to_update = []
        for product_key in sorted(included_keys):
            values = prepared[product_key]
            source = values["original"]
            obj = existing_classifications.get(product_key)
            if obj is None:
                obj = ParserProductClassification(product_key=product_key)
                to_create.append(obj)
            else:
                to_update.append(obj)
            obj.category = values["category"]
            obj.subcategory = values["subcategory"]
            obj.subcategory_type = values["subcategory_type"]
            obj.material = values["material"] or None
            obj.color = values["color"] or None
            obj.modification = source.modification or None
            obj.item_type = values["item_type"]
            obj.url = source.url or None
            obj.image = source.image or None
            obj.status = ParserProductClassification.STATUS_ACTIVE
            obj.match_type = ParserProductClassification.MATCH_TYPE_MANUAL
            obj.date_update = now
        if to_create:
            ParserProductClassification.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            ParserProductClassification.objects.bulk_update(
                to_update,
                fields=(
                    "category", "subcategory", "subcategory_type", "material", "color",
                    "modification", "item_type", "url", "image", "status", "match_type",
                    "date_update",
                ),
                batch_size=500,
            )

        eligible_pair_rows = list(AnalyticsProductMatchCandidate.objects.filter(
            application=application, is_eligible=True,
            product_key_base__in=included_keys,
            product_key_competitor__in=included_keys,
        ).exclude(competitor_source="base").values_list(
            "product_key_base", "product_key_competitor"
        ))
        competitor_groups, competitor_group_key_by_product = (
            build_competitor_url_groups(
                prefixes_by_source=get_prefixes_by_source(),
            )
        )
        expanded_pairs = expand_eligible_match_pairs(
            eligible_pairs=eligible_pair_rows,
            included_keys=included_keys,
            competitor_groups=competitor_groups,
            competitor_group_key_by_product=competitor_group_key_by_product,
        )
        override_rows = list(
            IPriceCompetitorSelectionOverride.objects.filter(
                product_key_base__in=included_keys,
                product_key_competitor__in=included_keys,
            ).values_list(
                "product_key_base", "product_key_competitor", "selection_mode"
            )
        )
        expanded_pair_set = set(expanded_pairs)
        override_modes = {}
        for base_key, competitor_key, selection_mode in override_rows:
            pair = (base_key, competitor_key)
            override_modes[pair] = selection_mode
            base_values = prepared.get(base_key)
            competitor_values = prepared.get(competitor_key)
            same_classification = bool(
                base_values and competitor_values and all(
                    base_values.get(field) == competitor_values.get(field)
                    for field in (
                        "item_type", "category", "subcategory", "subcategory_type"
                    )
                )
            )
            if (
                selection_mode == IPriceCompetitorSelectionOverride.MODE_INCLUDE
                and same_classification
            ):
                expanded_pair_set.add(pair)
            elif selection_mode == IPriceCompetitorSelectionOverride.MODE_EXCLUDE:
                expanded_pair_set.discard(pair)
        expanded_pairs = sorted(expanded_pair_set)
        ParserProductMatch.objects.filter(status="active").update(status="inactive")
        match_batch = []
        match_count = 0
        for base_key, competitor_key in expanded_pairs:
            match_batch.append(ParserProductMatch(
                product_key_base=base_key,
                product_key_competitor=competitor_key,
                status=ParserProductMatch.STATUS_ACTIVE,
                match_type=(
                    ParserProductMatch.MATCH_TYPE_MANUAL
                    if override_modes.get((base_key, competitor_key))
                    == IPriceCompetitorSelectionOverride.MODE_INCLUDE
                    else ParserProductMatch.MATCH_TYPE_AUTO
                ),
            ))
            if len(match_batch) >= 1000:
                ParserProductMatch.objects.bulk_create(
                    match_batch,
                    update_conflicts=True,
                    update_fields=("status", "match_type"),
                    unique_fields=("product_key_base", "product_key_competitor"),
                )
                match_count += len(match_batch)
                match_batch.clear()
        if match_batch:
            ParserProductMatch.objects.bulk_create(
                match_batch,
                update_conflicts=True,
                update_fields=("status", "match_type"),
                unique_fields=("product_key_base", "product_key_competitor"),
            )
            match_count += len(match_batch)

        result = {
            "run_id": run.id,
            "classifications_applied": len(included_keys),
            "classifications_excluded": len(prepared) - len(included_keys),
            "matches_applied": match_count,
            "weighted_candidates_eligible": eligible_matches,
            "weighted_pairs_eligible": len(eligible_pair_rows),
            "regional_pairs_added": len(expanded_pairs) - len(set(eligible_pair_rows)),
        }
        result["application_id"] = application.id
        application.classifications_applied = len(included_keys)
        application.matches_applied = match_count
        application.result = result
        application.save(update_fields=(
            "classifications_applied", "matches_applied", "result",
        ))
        return result


def apply_analytics_product_classification(file_obj, *, filename="", user=None):
    with analytics_product_operation_lock():
        return _apply_analytics_product_classification_locked(
            file_obj,
            filename=filename,
            user=user,
        )
