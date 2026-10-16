from __future__ import annotations

from io import BytesIO
from typing import Any

from django.db.models import Prefetch
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from datasets.models import (
    IPriceSnapshot,
    IPriceSnapshotApproval,
    IPriceSnapshotRegion,
)


EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet"
)


def excel_safe_value(
    value: Any,
):
    """
    Приводит значения к формату, безопасному для openpyxl.

    В частности, удаляет timezone из datetime,
    поскольку Excel не поддерживает timezone-aware datetime.
    """

    if value is None:
        return None

    if hasattr(value, "tzinfo"):
        if value.tzinfo is not None:
            return value.replace(
                tzinfo=None,
            )

    return value


def get_current_approval(
    region: IPriceSnapshotRegion,
) -> IPriceSnapshotApproval | None:
    """
    Получает текущее утверждение из Prefetch.

    Дополнительный SQL-запрос обычно не выполняется.
    """

    approvals = getattr(
        region,
        "prefetched_current_approvals",
        None,
    )

    if approvals is not None:
        return (
            approvals[0]
            if approvals
            else None
        )

    return (
        region.approvals
        .filter(
            is_current=True,
        )
        .select_related(
            "approved_by",
        )
        .order_by(
            "-revision",
            "-id",
        )
        .first()
    )


def get_effective_prices(
    region: IPriceSnapshotRegion,
) -> dict:
    """
    Возвращает итоговые цены региональной строки.

    Если существует ручное утверждение:
        используются approved_*.

    Иначе:
        используются default_approved_rrp
        и calculated_*.
    """

    approval = get_current_approval(
        region
    )
    tiers = ('small', 'medium', 'large') if region._meta.app_label == 'select_market' else ('distr', 'distr_1', 'small', 'medium', 'large')

    if approval is not None:
        return {
            "approval_id": approval.id,
            "approval_revision": (
                approval.revision
            ),
            "approval_source": "manual",
            "approved_by": (
                approval.approved_by.username
                if approval.approved_by
                else None
            ),
            "approved_at": (
                approval.approved_at
            ),
            "approval_comment": (
                approval.comment
            ),
            "rrp": approval.approved_rrp,
            **{tier: getattr(approval, 'approved_' + tier) for tier in tiers},
        }

    return {
        "approval_id": None,
        "approval_revision": None,
        "approval_source": "calculated",
        "approved_by": None,
        "approved_at": None,
        "approval_comment": "",
        "rrp": region.default_approved_rrp,
        **{tier: getattr(region, 'calculated_' + tier) for tier in tiers},
    }


def apply_header_style(
    worksheet,
):
    """
    Оформляет заголовок Excel-листа.
    """

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="D9EAF7",
    )

    for cell in worksheet[1]:
        cell.font = Font(
            bold=True,
        )

        cell.fill = header_fill

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )


def apply_worksheet_dimensions(
    worksheet,
):
    """
    Настраивает фильтр, закрепление и ширину столбцов.
    """

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = (
        worksheet.dimensions
    )

    for column_cells in worksheet.columns:
        max_length = 0

        column_letter = get_column_letter(
            column_cells[0].column
        )

        for cell in column_cells:
            value = cell.value

            if value is None:
                continue

            value_length = len(
                str(value)
            )

            max_length = max(
                max_length,
                value_length,
            )

        worksheet.column_dimensions[
            column_letter
        ].width = min(
            max(
                max_length + 2,
                10,
            ),
            50,
        )


def append_snapshot_info_sheet(
    *,
    workbook: Workbook,
    snapshot: IPriceSnapshot,
    regions_count: int,
):
    """
    Добавляет лист с информацией о версии.
    """

    worksheet = workbook.active
    worksheet.title = "Snapshot"

    rows = [
        (
            "Параметр",
            "Значение",
        ),
        (
            "ID snapshot",
            snapshot.id,
        ),
        (
            "Версия",
            snapshot.display_version,
        ),
        (
            "Дата расчета",
            snapshot.calculation_date,
        ),
        (
            "Глобальный номер версии",
            snapshot.version_number,
        ),
        (
            "Версия за дату",
            snapshot.revision_for_date,
        ),
        (
            "Статус",
            snapshot.status,
        ),
        (
            "Текущая версия за дату",
            snapshot.is_current,
        ),
        (
            "Активный окончательный расчет",
            snapshot.is_active,
        ),
        (
            "Дата создания",
            excel_safe_value(
                snapshot.created_at
            ),
        ),
        (
            "Дата завершения",
            excel_safe_value(
                snapshot.finished_at
            ),
        ),
        (
            "Создал",
            (
                snapshot.created_by.username
                if snapshot.created_by
                else None
            ),
        ),
        (
            "Активировал",
            (
                snapshot.activated_by.username
                if snapshot.activated_by
                else None
            ),
        ),
        (
            "Дата активации",
            excel_safe_value(
                snapshot.activated_at
            ),
        ),
        (
            "Количество региональных строк",
            regions_count,
        ),
    ]

    for row in rows:
        worksheet.append(
            row
        )

    apply_header_style(
        worksheet
    )

    worksheet.column_dimensions[
        "A"
    ].width = 35

    worksheet.column_dimensions[
        "B"
    ].width = 40


def append_prices_sheet(
    *,
    workbook: Workbook,
    regions,
):
    """
    Основной итоговый лист с ценами.
    """

    worksheet = workbook.create_sheet(
        "Цены"
    )

    headers = [
        "Snapshot ID",
        "Версия",
        "Дата расчета",

        "Product key",
        "Код номенклатуры",
        "Наименование",

        "Код иерархии",
        "Иерархия",
        "Вид",
        "Категория номенклатуры",
        "Группа номенклатуры",

        "Внутренняя категория",
        "Подкатегория",
        "Тип подкатегории",

        "Тип позиции",
        "Метод расчета",

        "Материал",
        "Цвет",
        "Модификация",

        "Производство",
        "Регион продажи",

        "Месяц себестоимости",
        "Дата цены 1С",

        "Себестоимость",
        "Транспорт",
        "Количество в еврофуре",
        "Логистика на единицу",
        "Себестоимость с логистикой",

        "Текущая retail",
        "Текущая distr",
        "Текущая distr_1",
        "Текущая small",
        "Текущая medium",
        "Текущая large",

        "Количество конкурентов",
        "Минимальная цена конкурентов",
        "Максимальная цена конкурентов",
        "Медианная цена конкурентов",

        "Предварительная РРЦ",
        "Минимальная цена",
        "Расчетная РРЦ",

        "Итоговая утвержденная РРЦ",
        "Итоговая distr",
        "Итоговая distr_1",
        "Итоговая small",
        "Итоговая medium",
        "Итоговая large",

        "Источник итоговой цены",
        "Версия утверждения",
        "Утвердил",
        "Дата утверждения",
        "Комментарий",

        "Текущая маржа",
        "Расчетная маржа",
        "Отклонение текущей цены",

        "Статус расчета",
        "Предупреждения",
        "Ошибки",

        "URL",
        "Изображение",
    ]

    worksheet.append(
        headers
    )

    for region in regions:
        product = (
            region.snapshot_product
        )

        snapshot = (
            product.snapshot
        )

        effective = get_effective_prices(
            region
        )

        worksheet.append([
            snapshot.id,
            snapshot.display_version,
            snapshot.calculation_date,

            product.base_product_key,
            product.code_1c,
            product.nom,

            product.nom_hier_code,
            product.nom_hier,
            product.nom_view,
            product.nom_category,
            product.nom_group,

            product.category,
            product.subcategory,
            product.subcategory_type,

            product.item_type,
            product.pricing_method,

            product.material,
            product.color,
            product.modification,

            region.departure,
            region.sale_region,

            region.product_cost_month,
            region.nomenclature_price_date,

            region.product_cost,
            region.transport_cost,
            region.quantity_eurotruck,
            region.logistics_unit,
            region.cost_with_logistics,

            region.current_retail,
            region.current_distr,
            region.current_distr_1,
            region.current_small,
            region.current_medium,
            region.current_large,

            region.regional_competitor_count,
            region.regional_competitor_rrp_min,
            region.regional_competitor_rrp_max,
            region.regional_competitor_rrp_median,

            region.preliminary_rrp,
            region.minimum_price,
            region.calculated_rrp,

            effective["rrp"],
            effective["distr"],
            effective["distr_1"],
            effective["small"],
            effective["medium"],
            effective["large"],

            effective["approval_source"],
            effective["approval_revision"],
            effective["approved_by"],
            excel_safe_value(
                effective["approved_at"]
            ),
            effective["approval_comment"],

            region.margin_current,
            region.margin_calculated,
            region.current_vs_calculated_percent,

            region.calculation_status,
            ", ".join(
                region.warning_codes or []
            ),
            ", ".join(
                region.error_codes or []
            ),

            product.url,
            product.image,
        ])

    apply_header_style(
        worksheet
    )

    apply_worksheet_dimensions(
        worksheet
    )


def append_errors_sheet(
    *,
    workbook: Workbook,
    regions,
):
    """
    Добавляет лист с ошибочными и проблемными строками.
    """

    worksheet = workbook.create_sheet(
        "Ошибки"
    )

    headers = [
        "Region row ID",
        "Product key",
        "Код номенклатуры",
        "Наименование",
        "Производство",
        "Регион продажи",
        "Статус",
        "Предупреждения",
        "Ошибки",
    ]

    worksheet.append(
        headers
    )

    for region in regions:
        if (
            region.calculation_status
            == IPriceSnapshotRegion.STATUS_SUCCESS
            and not region.warning_codes
            and not region.error_codes
        ):
            continue

        product = (
            region.snapshot_product
        )

        worksheet.append([
            region.id,
            product.base_product_key,
            product.code_1c,
            product.nom,
            region.departure,
            region.sale_region,
            region.calculation_status,
            ", ".join(
                region.warning_codes or []
            ),
            ", ".join(
                region.error_codes or []
            ),
        ])

    apply_header_style(
        worksheet
    )

    apply_worksheet_dimensions(
        worksheet
    )


def export_iprice_snapshot_to_excel(
    *,
    snapshot: IPriceSnapshot,
) -> BytesIO:
    """
    Формирует итоговую XLSX-выгрузку snapshot.
    """

    approval_model = IPriceSnapshotApproval
    region_model = IPriceSnapshotRegion
    is_select_market = snapshot._meta.app_label == "select_market"
    if is_select_market:
        from select_market.iprice_domain_models import (
            IPriceSnapshotApproval as approval_model,
            IPriceSnapshotRegion as region_model,
        )

    current_approvals_queryset = (
        approval_model.objects
        .filter(
            is_current=True,
        )
        .select_related(
            "approved_by",
        )
        .order_by(
            "-revision",
            "-id",
        )
    )

    regions = list(
        region_model.objects
        .filter(
            snapshot_product__snapshot=(
                snapshot
            ),
        )
        .select_related(
            "snapshot_product",
            "snapshot_product__snapshot",
            "snapshot_product__snapshot__created_by",
            "snapshot_product__snapshot__activated_by",
        )
        .prefetch_related(
            Prefetch(
                "approvals",
                queryset=(
                    current_approvals_queryset
                ),
                to_attr=(
                    "prefetched_current_approvals"
                ),
            )
        )
        .order_by(
            "snapshot_product__code_1c",
            "sale_region",
            "historical_variant" if is_select_market else "departure",
            "id",
        )
    )

    if not regions:
        raise ValueError(
            (
                "Snapshot does not contain "
                "regional rows"
            )
        )

    workbook = Workbook()

    append_snapshot_info_sheet(
        workbook=workbook,
        snapshot=snapshot,
        regions_count=len(regions),
    )

    if is_select_market:
        from select_market.iprice_export import append_prices
        append_prices(workbook=workbook, regions=regions)
    else:
        append_prices_sheet(workbook=workbook, regions=regions)
        append_errors_sheet(workbook=workbook, regions=regions)

    file_obj = BytesIO()

    if is_select_market:
        # Source strings (including textual 1C codes) are never Excel formulas.
        for sheet in workbook:
            for row in sheet:
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"

    try:
        workbook.save(file_obj)
    finally:
        workbook.close()

    file_obj.seek(0)

    return file_obj
