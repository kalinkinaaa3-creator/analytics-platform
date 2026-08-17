from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path

from django.conf import settings
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import PatternFill

from django.db.models import Count, OuterRef, Subquery

from datasets.models import (
    AnalyticsProductAnalysisResult,
    AnalyticsProductMatchCandidate,
    AnalyticsProductProcessingRun,
    AnalyticsProductScoringThreshold,
)
from datasets.services.parsers.analytics_product_processor import (
    MODIFICATION_NOT_DETERMINED,
)

EXCEL_TEXT_LIMIT = 32767
QUERY_CHUNK_SIZE = 500
WILDCARD_COLOR_VALUE = "__ANY__"
WILDCARD_COLOR_LABEL = "Любой цвет (по запросу)"

PRODUCT_COLUMNS = (
    "product_key", "source", "product_name", "url", "image", "item_type",
    "category", "subcategory", "subcategory_type", "classification_status",
    "classification_score", "classification_available_weight",
    "classification_matched_weight", "modification", "modification_code",
    "best_match_product_key", "best_match_name", "match_score",
    "match_coverage", "second_match_product_key", "second_match_name",
    "second_match_score", "match_gap", "match_status", "control_reasons",
    "normalized_properties", "classification_evidence", "match_evidence", "date_add",
)
CONTROL_COLUMNS = (
    "product_key", "source", "product_name", "url", "item_type", "category",
    "subcategory", "subcategory_type", "classification_status",
    "classification_score", "modification", "modification_code",
    "best_match_product_key", "best_match_name", "match_score",
    "match_coverage", "second_match_product_key", "second_match_name",
    "second_match_score", "match_gap", "match_status", "control_reasons",
    "control_explanation",
    "normalized_properties", "classification_evidence", "match_evidence",
)
IPRICE_CLASSIFICATION_COLUMNS = (
    "calculation_version", "include", "product_key", "product_name", "source",
    "category", "subcategory", "subcategory_type", "material", "color",
    "modification", "item_type", "automatic_status", "classification_score",
    "matches_found", "control_reason",
)
CANDIDATE_COLUMNS = (
    "product_key_base", "base_product_name", "product_key_competitor",
    "competitor_product_name", "competitor_source", "match_score",
    "match_coverage", "is_eligible", "threshold_status", "control_reasons",
    "match_evidence",
)

CONTROL_REASON_EXPLANATIONS = {
    "NO_SUBCATEGORY": "Не найдено правило определения subcategory.",
    "AMBIGUOUS_CLASSIFICATION": "Несколько классификаций имеют одинаковый приоритет и специфичность.",
    "SUBCATEGORY_TYPE_NOT_DEFINED": "Для subcategory предусмотрен subcategory_type, но определить его не удалось.",
    "LOW_CLASSIFICATION_SCORE": "Classification score находится в диапазоне ручной проверки.",
    "UNCLASSIFIED": "Classification score ниже минимального надёжного уровня.",
    "MATCH_PROFILE_NOT_FOUND": "Не найден профиль весов matching для определённого класса.",
    "NO_MATCH": "В том же классе не найдено кандидатов конкурентных источников.",
    "LOW_MATCH_SCORE": "Match score не прошёл активный порог scoring_thresholds.",
    "LOW_MATCH_COVERAGE": "Покрытие свойств не прошло активный порог scoring_thresholds.",
    "STRICT_PROPERTY_MISMATCH": (
        "Значение обязательного свойства отличается у товаров."
    ),
    "STRICT_PROPERTY_MISSING_BASE": (
        "У товара iPrice не найдено значение обязательного свойства."
    ),
    "STRICT_PROPERTY_MISSING_COMPETITOR": (
        "У товара конкурента не найдено значение обязательного свойства."
    ),
    "AMBIGUOUS_MATCH": "Кандидаты близки по активному порогу match_gap.",
    "MODIFICATION_NOT_DEFINED": (
        "Не найдены свойства с положительными весами matching_score "
        "для формирования модификации."
    ),
}


def _excel_value(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif hasattr(value, "isoformat"):
        value = value.isoformat()
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        value = str(value)
    if isinstance(value, str) and len(value) > EXCEL_TEXT_LIMIT:
        value = value[:EXCEL_TEXT_LIMIT - 20] + "…[truncated]"
    # External product data must never become an executable Excel formula.
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        value = "'" + value
    return value


def _append_queryset_sheet(workbook, title, columns, queryset):
    worksheet = workbook.create_sheet(title=title)
    worksheet.append(columns)
    for row in queryset.values(*columns).iterator(chunk_size=QUERY_CHUNK_SIZE):
        worksheet.append([_excel_value(row.get(column)) for column in columns])


def _append_control_sheet(workbook, queryset):
    worksheet = workbook.create_sheet(title="product_control")
    worksheet.append(CONTROL_COLUMNS)
    db_columns = tuple(
        column for column in CONTROL_COLUMNS if column != "control_explanation"
    )
    for row in queryset.values(*db_columns).iterator(chunk_size=QUERY_CHUNK_SIZE):
        reasons = row.get("control_reasons") or []
        explanation = " ".join(
            CONTROL_REASON_EXPLANATIONS.get(reason, str(reason)) for reason in reasons
        )
        row["control_explanation"] = explanation
        worksheet.append([_excel_value(row.get(column)) for column in CONTROL_COLUMNS])


def _append_iprice_classification_sheet(workbook, run, queryset):
    worksheet = workbook.create_sheet(title="iprice_classification")
    worksheet.append(IPRICE_CLASSIFICATION_COLUMNS)
    match_counts = {
        row["product_key_base"]: row["count"]
        for row in (
            AnalyticsProductMatchCandidate.objects.filter(
                run=run, application__isnull=True, is_eligible=True
            )
            .values("product_key_base")
            .annotate(count=Count("id"))
        )
    }
    columns = (
        "product_key", "product_name", "source", "category", "subcategory",
        "subcategory_type", "normalized_properties", "modification", "item_type",
        "classification_status", "classification_score", "control_reasons",
    )
    for row in queryset.values(*columns).iterator(chunk_size=QUERY_CHUNK_SIZE):
        properties = row.get("normalized_properties") or {}
        reasons = row.get("control_reasons") or []
        prepared = {
            "calculation_version": run.id,
            "include": "Да",
            "product_key": row["product_key"],
            "product_name": row["product_name"],
            "source": row["source"],
            "category": row["category"],
            "subcategory": row["subcategory"],
            "subcategory_type": row["subcategory_type"],
            "material": properties.get("material"),
            "color": (
                WILDCARD_COLOR_LABEL
                if properties.get("color") == WILDCARD_COLOR_VALUE
                else properties.get("color")
            ),
            "modification": row["modification"],
            "item_type": row["item_type"],
            "automatic_status": row["classification_status"],
            "classification_score": row["classification_score"],
            "matches_found": match_counts.get(row["product_key"], 0),
            "control_reason": " ".join(
                CONTROL_REASON_EXPLANATIONS.get(reason, str(reason))
                for reason in reasons
            ),
        }
        output_row = []
        for column in IPRICE_CLASSIFICATION_COLUMNS:
            value = _excel_value(prepared.get(column))
            if column == "modification" and value == MODIFICATION_NOT_DETERMINED:
                cell = WriteOnlyCell(worksheet, value=value)
                cell.fill = PatternFill("solid", fgColor="FFF2CC")
                output_row.append(cell)
            else:
                output_row.append(value)
        worksheet.append(output_row)


def _append_match_candidates_sheet(workbook, run):
    worksheet = workbook.create_sheet(title="match_candidates")
    worksheet.append(CANDIDATE_COLUMNS)
    names = AnalyticsProductAnalysisResult.objects.filter(
        run=run,
        product_key=OuterRef("product_key_base"),
    ).values("product_name")[:1]
    competitor_names = AnalyticsProductAnalysisResult.objects.filter(
        run=run,
        product_key=OuterRef("product_key_competitor"),
    ).values("product_name")[:1]
    queryset = (
        AnalyticsProductMatchCandidate.objects
        .filter(run=run, application__isnull=True)
        .annotate(
            base_product_name=Subquery(names),
            competitor_product_name=Subquery(competitor_names),
        )
        .order_by(
            "product_key_base", "-is_eligible", "-match_score",
            "-match_coverage", "competitor_source", "product_key_competitor",
        )
    )
    for row in queryset.values(*CANDIDATE_COLUMNS).iterator(
        chunk_size=QUERY_CHUNK_SIZE
    ):
        worksheet.append([
            _excel_value(row.get(column))
            for column in CANDIDATE_COLUMNS
        ])


def _append_iprice_instructions_sheet(workbook):
    worksheet = workbook.create_sheet(title="iprice_instructions")
    worksheet.append(("Правило", "Пояснение"))
    instructions = (
        ("Рабочий лист", "Для ручной загрузки используется только лист iprice_classification."),
        ("Полнота файла", "Нельзя удалять строки: в файле должны остаться все товары расчёта."),
        ("Неизменяемые поля", "Не изменяйте calculation_version, product_key и source."),
        ("include=Да", "Товар применяется. Обязательны category, subcategory, subcategory_type, material, color и item_type. Модификация пересчитывается автоматически."),
        ("include=Нет", "Товар исключается из активной классификации и matching."),
        ("Статусы", "Можно загружать classified, review и unclassified: для include=Да предварительно заполните обязательные поля."),
        ("Matching", "После успешной ручной загрузки matching пересчитывается по текущим весам и порогам."),
        ("Модификация", "Формируется только по свойствам с весом > 0 в matching_score; material и color в текст не дублируются."),
        ("Не определено автоматически", "Файл можно загрузить как есть; значение сохраняет предупреждение о ненайденных взвешенных свойствах."),
        ("Кандидаты", "Лист match_candidates содержит все рассчитанные пары; is_eligible=Да означает прохождение match_score и match_coverage."),
        ("match_gap", "Показывает близость лучших кандидатов и является информационным для many-to-many."),
        ("Любой цвет", f"Значение «{WILDCARD_COLOR_LABEL}» является допустимым wildcard и совпадает с любым цветом."),
    )
    for row in instructions:
        worksheet.append(tuple(_excel_value(value) for value in row))


def _latest_successful_run():
    return (
        AnalyticsProductProcessingRun.objects
        .filter(status=AnalyticsProductProcessingRun.STATUS_SUCCESS)
        .order_by("-finished_at", "-id").first()
    )


def _build_product_url_control_workbook(
    *, run_id=None, summary_status=None, summary_finished_at=None
):
    run = (
        AnalyticsProductProcessingRun.objects.select_related("directory_load").get(pk=run_id)
        if run_id is not None else _latest_successful_run()
    )
    if run is None:
        raise ValueError("Нет успешно завершённого analytics product запуска")
    if not hasattr(run, "directory_load"):
        run = AnalyticsProductProcessingRun.objects.select_related("directory_load").get(pk=run.pk)

    products = AnalyticsProductAnalysisResult.objects.filter(run=run).order_by(
        "source", "product_key"
    )
    control = products.exclude(control_reasons=[])

    # write_only keeps exported cells out of process memory.
    workbook = Workbook(write_only=True)
    _append_queryset_sheet(workbook, "product_analysis", PRODUCT_COLUMNS, products)
    _append_control_sheet(workbook, control)

    summary = workbook.create_sheet(title="run_summary")
    summary.append(("parameter", "value", "explanation"))
    threshold_summary = {
        row.metric: (
            f"{row.min_value if row.min_value is not None else '−∞'}–"
            f"{row.max_value if row.max_value is not None else '+∞'}; {row.auto_action}"
        )
        for row in AnalyticsProductScoringThreshold.objects.filter(
            auto_action__in=(
                "auto_accept", "auto_match", "auto_match_allowed",
                "require_exact_match",
            )
        )
    }
    summary_rows = (
        ("run_id", run.id, "Идентификатор фонового запуска"),
        ("run_status", summary_status or run.status, "Статус обработки"),
        ("started_at", run.started_at, "Начало обработки"),
        ("finished_at", summary_finished_at or run.finished_at, "Завершение обработки"),
        ("directory_load_id", run.directory_load_id, "Версия загрузки справочника"),
        ("directory_filename", run.directory_load.filename, "Имя исходного справочника"),
        ("directory_checksum", run.directory_load.checksum, "SHA-256 справочника"),
        ("all_products", products.count(), "Все товары источников текущего directory"),
        ("control_products", control.count(), "Товары, требующие контроля"),
        ("classified", products.filter(classification_status="classified").count(),
         "Классификация принята автоматически"),
        ("review", products.filter(classification_status="review").count(),
         "Требуется ручная проверка"),
        ("unclassified", products.filter(classification_status="unclassified").count(),
         "Надёжная классификация не определена"),
        ("auto_matched", products.filter(match_status="matched").count(),
         "Кандидаты нового процесса; ParserProductMatch не изменён"),
        ("classification_threshold", threshold_summary.get("classification_score", "—"),
         "Активный диапазон автоматической классификации"),
        ("match_threshold", threshold_summary.get("match_score", "—"),
         "Активный диапазон автоматического кандидата match"),
        ("coverage_threshold", threshold_summary.get("match_coverage", "—"),
         "Активный диапазон покрытия свойств"),
        ("mandatory_property_weight",
         threshold_summary.get("matching_property_weight", "—"),
         "Вес, начиная с которого несовпадение свойства исключает кандидата"),
        ("gap_threshold", threshold_summary.get("match_gap", "—"),
         "Информационный диапазон явного отрыва"),
    )
    for key, value, explanation in summary_rows:
        summary.append((key, _excel_value(value), explanation))

    _append_iprice_classification_sheet(workbook, run, products)
    _append_match_candidates_sheet(workbook, run)
    _append_iprice_instructions_sheet(workbook)

    return workbook


def build_product_url_control_excel(*, run_id=None) -> BytesIO:
    """Compatibility API for callers that explicitly need an in-memory file."""
    output = BytesIO()
    _build_product_url_control_workbook(run_id=run_id).save(output)
    output.seek(0)
    return output


def save_product_url_control_excel(
    *, run_id=None, summary_status=None, summary_finished_at=None
):
    output_dir = Path(settings.BASE_DIR) / "media" / "datasets"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "parser_product_url_control_latest.xlsx"
    temporary = target.with_suffix(".xlsx.tmp")
    workbook = _build_product_url_control_workbook(
        run_id=run_id,
        summary_status=summary_status,
        summary_finished_at=summary_finished_at,
    )
    with open(temporary, "wb") as file_obj:
        workbook.save(file_obj)
        file_obj.flush()
        os.fsync(file_obj.fileno())
    os.replace(temporary, target)
    return target
