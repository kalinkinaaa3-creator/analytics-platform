import io
import os

import pandas as pd

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse


def dataframe_to_excel_response(df, filename, sheet_name):
    output = io.BytesIO()

    df.to_excel(output, index=False, sheet_name=sheet_name)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


def export_wordstat_to_excel(rows, filename="wordstat.xlsx"):
    column_aliases = {
        "feature": "Категория",
        "category": "Подкатегория",
        "phrase": "Запрос",
        "year": "Год",

        "month_1": "Январь",
        "month_2": "Февраль",
        "month_3": "Март",
        "month_4": "Апрель",
        "month_5": "Май",
        "month_6": "Июнь",
        "month_7": "Июль",
        "month_8": "Август",
        "month_9": "Сентябрь",
        "month_10": "Октябрь",
        "month_11": "Ноябрь",
        "month_12": "Декабрь",

        "total": "Итого",
        "average": "Среднее",
        "growth": "Рост",

        "monthS_1": "Январь сез-ть",
        "monthS_2": "Февраль сез-ть",
        "monthS_3": "Март сез-ть",
        "monthS_4": "Апрель сез-ть",
        "monthS_5": "Май сез-ть",
        "monthS_6": "Июнь сез-ть",
        "monthS_7": "Июль сез-ть",
        "monthS_8": "Август сез-ть",
        "monthS_9": "Сентябрь сез-ть",
        "monthS_10": "Октябрь сез-ть",
        "monthS_11": "Ноябрь сез-ть",
        "monthS_12": "Декабрь сез-ть",

        "desktop": "Desktop",
        "phone": "Phone",
        "tablet": "Tablet",
        "other_device": "Other device",

        "ekb_macroregion": "ЕКБ рег.",
        "kras_macroregion": "КРД рег.",
        "mos_macroregion": "МСК рег.",
        "nign_macroregion": "НК рег.",
        "novos_macroregion": "НВС рег.",
        "spb_macroregion": "СПБ рег.",
        "sng_macroregion": "СНГ рег.",
        "other_macroregion": "Другие рег.",
    }

    export_columns = list(column_aliases.keys())

    data_for_export = [
        {
            column: row.get(column)
            for column in export_columns
        }
        for row in rows
    ]

    df = pd.DataFrame(data_for_export)
    df = df.rename(columns=column_aliases)

    if not df.empty:
        numeric_columns = [
            column_aliases[column]
            for column in export_columns
            if column not in ("feature", "category", "phrase")
        ]

        for column in numeric_columns:
            if column in df.columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                ).fillna(0)

    return dataframe_to_excel_response(
        df=df,
        filename=filename,
        sheet_name="Wordstat",
    )




def export_purchases_to_excel(purchases_list, filename="purchases.xlsx"):
    column_aliases = {
        "month_year": "Год-Месяц",
        "nomenclature_code": "Группа",
        "nomenclature": "Номенклатура",
        "partner": "Партнер",
        "quantity_1C": "Количество, кг",
        "revenue_1C": "Стоимость, руб",
        "price": "Цена, руб/кг",
    }

    data_for_export = [
        {
            "month_year": row.get("month_year"),
            "nomenclature_code": row.get("nomenclature_code"),
            "nomenclature": row.get("nomenclature"),
            "partner": row.get("partner"),
            "quantity_1C": row.get("quantity_1C"),
            "revenue_1C": row.get("revenue_1C"),
            "price": row.get("price"),
        }
        for row in purchases_list
    ]

    df = pd.DataFrame(data_for_export)
    df = df.rename(columns=column_aliases)

    if not df.empty:
        df["Количество, кг"] = pd.to_numeric(df["Количество, кг"], errors="coerce").fillna(0).astype(int)
        df["Стоимость, руб"] = pd.to_numeric(df["Стоимость, руб"], errors="coerce").fillna(0).round(2)
        df["Цена, руб/кг"] = pd.to_numeric(df["Цена, руб/кг"], errors="coerce").fillna(0).round(2)

    return dataframe_to_excel_response(
        df=df,
        filename=filename,
        sheet_name="Сырье",
    )


def export_turnover_to_excel(turnover_list, filename="turnover.xlsx"):
    column_aliases = {
        "month_year": "Год-Месяц",
        "nomenclature": "Номенклатура",
        "warehouse_group": "Группа по складу",
        "warehouse": "Склад",
        "quantity": "Качество",
        "middle_stock": "Средний запас, шт",
        "middle_rubstock": "Средний запас, руб",
    }

    data_for_export = [
        {
            "month_year": row.get("month_year"),
            "nomenclature": row.get("nomenclature") or "—",
            "warehouse_group": row.get("warehouse_group") or "—",
            "warehouse": row.get("warehouse") or "—",
            "quantity": row.get("quantity") or "—",
            "middle_stock": row.get("middle_stock") or 0,
            "middle_rubstock": row.get("middle_rubstock") or 0,
        }
        for row in turnover_list
    ]

    df = pd.DataFrame(data_for_export)
    df = df.rename(columns=column_aliases)

    if not df.empty:
        df["Средний запас, шт"] = pd.to_numeric(df["Средний запас, шт"], errors="coerce").fillna(0).round(2)
        df["Средний запас, руб"] = pd.to_numeric(df["Средний запас, руб"], errors="coerce").fillna(0).round(2)

        df["month_year_sort"] = pd.to_datetime(df["Год-Месяц"])
        df = df.sort_values(
            ["month_year_sort", "Средний запас, руб"],
            ascending=[False, False],
        )
        df = df.drop("month_year_sort", axis=1)

    return dataframe_to_excel_response(
        df=df,
        filename=filename,
        sheet_name="Остатки",
    )


def export_accreceiv_to_excel(accreceiv_list, filename="accreceiv.xlsx"):
    column_aliases = {
        "month_year": "Год-Месяц",
        "partner": "Контрагент",
        "contract_partner": "Договор",
        "manager_name": "Менеджер",
        "final_stock": "Сумма (руб.): кон. остаток",
    }

    data_for_export = [
        {
            "month_year": row.get("month_year"),
            "partner": row.get("partner"),
            "contract_partner": row.get("contract_partner"),
            "manager_name": row.get("manager_name"),
            "final_stock": row.get("final_stock"),
        }
        for row in accreceiv_list
    ]

    df = pd.DataFrame(data_for_export)
    df = df.rename(columns=column_aliases)

    if not df.empty:
        df["Сумма (руб.): кон. остаток"] = pd.to_numeric(
            df["Сумма (руб.): кон. остаток"],
            errors="coerce",
        ).fillna(0).round(2)

    return dataframe_to_excel_response(
        df=df,
        filename=filename,
        sheet_name="ДЗ",
    )






def export_revenue_to_excel(rows, filename="revenue.xlsx"):
    column_aliases = {
        "date": "Дата",
        "direction": "Направление",
        "project": "Проект",
        "manager": "Менеджер",
        "partner": "Контрагент",
        "partner_code": "Код контрагента",
        "consignee": "Грузополучатель",
        "nom_view": "Вид продукции",
        "nom_category": "Категория",
        "nom_group": "Группа",
        "nom": "Номенклатура",
        "nom_code": "Код номенклатуры",
        "type_doc": "Документ-регистратор",
        "quantity": "Количество",
        "weight_total": "Вес",
        "revenue": "Выручка",
        "is_new_sku": "Новый SKU",
        "is_new_client": "Новый клиент",
    }

    export_columns = list(column_aliases.keys())

    data_for_export = [
        {
            column: row.get(column)
            for column in export_columns
        }
        for row in rows
    ]

    df = pd.DataFrame(data_for_export)
    df = df.rename(columns=column_aliases)

    if not df.empty:
        numeric_columns = [
            "Код контрагента",
            "Код номенклатуры",
            "Количество",
            "Вес",
            "Выручка",
        ]

        for column in numeric_columns:
            if column in df.columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                ).fillna(0)

        def format_bool(value):
            if value in (True, 1, "1", "true", "True", "TRUE", "t", "T", "yes", "Yes", "YES"):
                return "Да"

            return "Нет"

        df["Новый SKU"] = df["Новый SKU"].apply(format_bool)

        df["Новый клиент"] = df["Новый клиент"].apply(format_bool)

    return dataframe_to_excel_response(
        df=df,
        filename=filename,
        sheet_name="Выручка",
    )