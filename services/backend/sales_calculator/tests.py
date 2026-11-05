import io
from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest import TestCase as UnitTestCase
from unittest.mock import Mock, patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from dashboards.models import Dashboard, DashboardAccess
from .api import SettingsView, RefreshView, ProductsView
from .calculation import calculate
from .configuration import DEFAULTS, validate_config
from .export import export_document
from .models import SalesCalculatorRefresh
from .warehouse import decorate


def product(**changes):
    return {"product_key": 1, "code": 123, "name": "Товар", "region": "Москва",
            "name_1c": "Товар 1С", "price_list": "Товар прайса", "calculation_date": "2026-09-30",
            "retail": "100", "small": "90", "medium": "80", "large": "70",
            "characteristics": {}, "logistics": {}, "stocks": {}, "weight_value": "2", "pallet_value": "50", **changes}


class CalculationTests(UnitTestCase):
    def test_distributor_prices_vat_optional_values_and_default_order(self):
        config = validate_config({})
        columns = config["simple_columns"]
        start = columns.index("large_gross") + 1
        self.assertEqual(columns[start:start + 4], ["distr_net", "distr_gross", "distr_1_net", "distr_1_gross"])
        source = product(distr="60.5", distr_1="55.4")
        result = calculate({"1": source}, [{"product_key": 1}], config)
        row = result["rows"][0]
        self.assertEqual((row["distr_net"], row["distr_gross"], row["distr_1_net"], row["distr_1_gross"]),
                         (Decimal(61), Decimal("74.42"), Decimal(55), Decimal("67.10")))
        zero = calculate({"1": source}, [{"product_key": 1}], validate_config({"vat": 0}))["rows"][0]
        self.assertEqual(zero["distr_gross"], zero["distr_net"])
        absent = calculate({"1": product()}, [{"product_key": 1}], config)["rows"][0]
        self.assertIsNone(absent["distr_net"])
        self.assertIsNone(absent["distr_1_gross"])
        automatic = calculate({"1": source}, [{"product_key": 1, "quantity": 1000000}], config)
        self.assertEqual(automatic["automatic_type"], "large")
        self.assertIsNone(automatic["next_type"])
        manual = calculate({"1": source}, [{"product_key": 1, "price_type": "distr_1"}], config)
        self.assertEqual(manual["rows"][0]["unit_net"], 55)

    def test_distributor_exports_and_comparison(self):
        from openpyxl import load_workbook
        config = validate_config({"simple_columns": ["code", "distr_net", "distr_gross", "distr_1_net", "distr_1_gross"]})
        result = calculate({"1": product(distr="60", distr_1="50")}, [{"product_key": 1}], config)
        ws = load_workbook(export_document(result, config, "simple", "xlsx")).active
        self.assertEqual([ws.cell(4, col).value for col in range(3, 7)], [60, 73.2, 50, 61])
        self.assertNotIn("800", ws.cell(3, 3).value)
        self.assertEqual(export_document(result, config, "simple", "pdf").read(4), b"%PDF")
        result["warehouses"] = [{"region": "Main", "rows": result["rows"]}, {"region": "Missing", "rows": []}]
        ws = load_workbook(export_document(result, config, "simple", "xlsx")).active
        self.assertEqual(ws.cell(4, 3).value, "Main: 60\nMissing: —")
        self.assertEqual(export_document(result, config, "simple", "pdf").read(4), b"%PDF")

    def test_existing_column_visibility_is_preserved_with_new_price_order(self):
        old_order = ["code", "large_net", "large_gross", "url"]
        config = validate_config({"simple_column_order": old_order, "simple_columns": ["code", "large_gross"]})
        self.assertEqual(config["simple_columns"], ["code", "large_gross"])
        self.assertEqual(config["simple_column_order"][:8], ["code", "large_net", "large_gross", "distr_net", "distr_gross", "distr_1_net", "distr_1_gross", "url"])

    def test_comparison_exports_preserve_warehouses_prices_and_missing_products(self):
        from openpyxl import load_workbook
        from reportlab.platypus import Table
        for mode, keys in (("simple", ["retail_gross", "retail_net"]), ("full", ["sum_gross", "unit_net"])):
            with self.subTest(mode=mode):
                config = validate_config({mode + "_columns": [*keys, "code"], mode + "_column_order": [*keys, "code"]})
                result = calculate({"1": product()}, [{"product_key": 1, "quantity": 2}], config)
                other = calculate({"1": product(retail="200", region="Other")}, [{"product_key": 1, "quantity": 2}], config)
                result["warehouses"] = [
                    {"region": "Main", "rows": result["rows"]},
                    {"region": "Other", "rows": other["rows"]},
                    {"region": "Missing", "rows": []},
                ]
                from .export import price_text
                ws = load_workbook(export_document(result, config, mode, "xlsx")).active
                for index, key in enumerate(keys, 2):
                    self.assertEqual(ws.cell(4, index).value,
                                     f'Main: {price_text(result["rows"][0][key])}\nOther: {price_text(other["rows"][0][key])}\nMissing: —')
                    self.assertTrue(ws.cell(4, index).alignment.wrap_text)
                paragraphs = []
                original = Table.drawOn
                def record(table, canvas, *args, **kwargs):
                    if table.repeatRows == 1:
                        for row in table._cellvalues:
                            for cell in row:
                                if isinstance(cell, (tuple, list)) and cell:
                                    paragraphs.append(cell[0].getPlainText())
                    return original(table, canvas, *args, **kwargs)
                with patch.object(Table, "drawOn", record):
                    document = export_document(result, config, mode, "pdf")
                self.assertEqual(document.read(4), b"%PDF")
                text = "\n".join(paragraphs)
                for key in keys:
                    self.assertIn(f'Other: {price_text(other["rows"][0][key])}', text)
                self.assertIn("Missing: —", text)
                self.assertNotIn("_warehouse_prices", result["rows"][0])

    def test_quantity_default_only_changes_price_and_preserves_saved_choice(self):
        self.assertNotIn("quantity", validate_config({})["simple_columns"])
        self.assertIn("quantity", validate_config({})["full_columns"])
        self.assertIn("quantity", validate_config({"simple_columns": ["quantity"]})["simple_columns"])

    def test_pdf_reordered_columns_repeat_headers_and_keep_product_rows_together(self):
        from reportlab.platypus import Table
        original = Table.drawOn
        for mode in ("simple", "full"):
            price_key = "large_gross" if mode == "simple" else "unit_gross"
            for columns in (["code", "name", "characteristics", price_key],
                            [price_key, "characteristics", "name", "code"]):
                with self.subTest(mode=mode, columns=columns):
                    pages = []
                    def record(table, canvas, *args, **kwargs):
                        if table.repeatRows == 1:
                            pages.append((canvas.getPageNumber(), list(table._colWidths),
                                          [[cell[0].getPlainText() if isinstance(cell, (tuple, list)) and cell else str(cell)
                                            for cell in row] for row in table._cellvalues]))
                        return original(table, canvas, *args, **kwargs)
                    config = validate_config({mode + "_columns": columns, mode + "_column_order": columns})
                    products = {str(i): product(product_key=i, code=i, characteristics={"equipment": "Long characteristic " * 45}) for i in range(1, 31)}
                    result = calculate(products, [{"product_key": i} for i in products], config)
                    with patch.object(Table, "drawOn", record):
                        document = export_document(result, config, mode, "pdf")
                    self.assertEqual(document.read(4), b"%PDF")
                    self.assertGreater(len(pages), 1)
                    for _, widths, rows in pages:
                        self.assertEqual(widths, pages[0][1])
                        self.assertEqual(rows[0], pages[0][2][0])
                    self.assertEqual([row[0] for _, _, rows in pages for row in rows[1:]], [str(i) for i in range(1, 31)])

    def test_column_visibility_does_not_change_default_or_custom_order(self):
        from openpyxl import load_workbook
        for mode in ("simple", "full"):
            field, order = mode + "_columns", mode + "_column_order"
            config = validate_config({field: ["name", "image", "code"]})
            self.assertEqual(config[field], ["image", "code", "name"])
            config = validate_config({field: ["image", "name"], order: ["name", "code", "image"]})
            config[field].append("code")
            restored = validate_config(config)
            self.assertEqual(restored[field], ["name", "code", "image"])
            self.assertEqual(restored[order][:3], ["name", "code", "image"])
            result = calculate({"1": product()}, [{"product_key": 1}], restored)
            ws = load_workbook(export_document(result, restored, mode, "xlsx")).active
            self.assertEqual(ws['B3'].value, 'Номенклатура прайс-листа')
            self.assertEqual(ws['C3'].value, 'Артикул')
        with self.assertRaises(ValueError):
            validate_config({"full_column_order": ["unknown"]})

    def test_missing_website_product_keeps_position_but_not_links(self):
        from .warehouse import build_rows
        from .export import display
        from openpyxl import load_workbook
        fields = ["product_key", "code", "website_available", "url", "image"]
        cursor = Mock()
        cursor.description = [(field,) for field in fields]
        cursor.fetchall.side_effect = [
            [(1, 123, False, "https://iplast.com/old", "https://iplast.com/old.png"),
             (2, 456, True, "https://iplast.com/current", "")], []]
        with patch("sales_calculator.warehouse.connection") as connection:
            connection.cursor.return_value.__enter__.return_value = cursor
            rows = build_rows(date(2026, 10, 7), False)
        params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(params[0].date(), date(2026, 10, 8))
        self.assertEqual(params[2].date(), date(2026, 10, 7))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], "")
        self.assertEqual(rows[0]["image"], "")
        self.assertEqual(rows[1]["url"], "https://iplast.com/current")
        self.assertEqual(display(rows[0], "url", {}), "")
        result = calculate({"1": product(**rows[0])}, [{"product_key": 1}], {})
        for mode in ("simple", "full"):
            config = validate_config({mode + "_columns": ["url"]})
            ws = load_workbook(export_document(result, config, mode, "xlsx")).active
            self.assertIsNone(ws["B4"].value)
            self.assertIsNone(ws["B4"].hyperlink)
            pdf = export_document(result, config, mode, "pdf").getvalue()
            self.assertNotIn(b"https://iplast.com/old", pdf)

    def test_export_numbers_follow_order_not_product_keys(self):
        from openpyxl import load_workbook
        products = {str(key): product(product_key=key) for key in (91, 7, 24)}
        result = calculate(products, [{"product_key": key} for key in (24, 91, 7)], {})
        for mode in ("simple", "full"):
            config = validate_config({mode + "_columns": ["name", "code"]})
            ws = load_workbook(export_document(result, config, mode, "xlsx")).active
            self.assertEqual(ws["A3"].value, "№")
            self.assertEqual([ws.cell(row, 1).value for row in (4, 5, 6)], [1, 2, 3])
            self.assertTrue(all(ws.cell(row, 1).data_type == "n" for row in (4, 5, 6)))
        self.assertNotIn("row_number", result["rows"][0])

    def test_branded_exports_fit_images_and_include_offer_totals(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from PIL import Image
        from openpyxl import load_workbook
        from django.test import override_settings
        image = io.BytesIO()
        Image.new("RGB", (120, 240), "white").save(image, format="PNG")
        row = product(image="https://iplast.com/a.png", url="https://iplast.com/item/", characteristics={"equipment": "Описание\n" * 12})
        result = calculate({"1": row}, [{"product_key": 1, "quantity": 3}], {})
        with TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            Image.new("RGBA", (240, 60), (0, 0, 0, 0)).save(Path(folder) / "logo.webp")
            for mode in ("simple", "full"):
                config = validate_config({mode + "_columns": ["image", "name", "characteristics", "url"]})
                with patch("sales_calculator.export.image_bytes", return_value=image.getvalue()):
                    ws = load_workbook(export_document(result, config, mode, "xlsx")).active
                    pdf = export_document(result, config, mode, "pdf")
                self.assertEqual(pdf.read(4), b"%PDF")
                self.assertIn('ООО "Ай-Пласт"', ws["A1"].value)
                self.assertEqual(ws["A1"].fill.fgColor.rgb, "00DC2F2F")
                self.assertIn("A1:E1", str(ws.merged_cells))
                self.assertEqual(ws["B3"].value, "Изображение")
                self.assertEqual(ws["E4"].value, "Посмотреть")
                self.assertIsNone(ws["B3"].fill.patternType)
                self.assertIsNone(ws["C4"].fill.patternType)
                self.assertEqual(len(ws._images), 1)
                anchor = ws._images[0].anchor
                self.assertAlmostEqual(anchor.ext.cx / anchor.ext.cy, .5)
                self.assertLessEqual(anchor._from.rowOff + anchor.ext.cy, ws.row_dimensions[4].height * 12700)
                self.assertLessEqual(anchor._from.colOff + anchor.ext.cx, 18 * 7 * 9525)
                if mode == "full":
                    self.assertEqual(ws["E5"].value, result["net"])
                    self.assertEqual(ws["E6"].value, result["vat"])
                    self.assertEqual(ws["E7"].value, result["gross"])
                else:
                    self.assertEqual(ws.max_row, 4)

    def test_optional_properties_and_defaults(self):
        from .properties import SOURCE_NAMES, VALUE_LABELS
        config = validate_config({})
        self.assertFalse(set(SOURCE_NAMES) & set(config["characteristics"]))
        self.assertNotIn("truck82_no_pallet", config["logistics"])
        self.assertIn("pallet", config["logistics"])
        self.assertEqual(validate_config({"characteristics": list(SOURCE_NAMES)})["characteristics"], list(SOURCE_NAMES))
        for key, source in SOURCE_NAMES.items():
            if key in VALUE_LABELS:
                for value, label in VALUE_LABELS[key].items():
                    row = decorate(product(), {source: value.upper()})
                    self.assertEqual(row["characteristics"][key], label)
                self.assertNotIn(key, decorate(product(), {source: None})["characteristics"])
            else:
                self.assertEqual(decorate(product(), {source: "-20"})["characteristics"][key], "-20")
        for source in ("Возможность вкладывания", "Возможность штабелирования"):
            self.assertFalse(decorate(product(), {source: "Нет"})["characteristics"].get("nestable"))

    def test_price_name_and_pallet_source_fallbacks(self):
        from .export import display
        for blank in (None, "", "   ", "—"):
            row = decorate(product(), {"Номенклатура прайс-листа": blank,
                "Количество на паллетоместе (для прайса)": blank,
                "Количество на паллете, шт.": "12", "Складирование": "99"})
            self.assertEqual(display(row, "name", {}), product()["name"])
            self.assertEqual(row["pallet_value"], "12")
            self.assertEqual(row["characteristics"]["storage"], "99")
        row = decorate(product(), {"Номенклатура прайс-листа": "Имя для прайса",
            "Количество на паллетоместе (для прайса)": "8", "Количество на паллете, шт.": "12"})
        self.assertEqual(display(row, "name", {}), "Имя для прайса")
        self.assertEqual(row["name"], product()["name"])
        self.assertEqual(calculate({"1": row}, [{"product_key": 1, "quantity": 17}], {})["logistics"]["pallets"], 3)
        self.assertIsNone(decorate(product(), {"Складирование": "99"})["pallet_value"])

    def test_property_spelling_and_export_selection(self):
        from openpyxl import load_workbook
        row = decorate(product(), {"Количество   колёс": "4", "Тип опоры": "Колёса",
            "Количество в еврофуре 82 м³, шт. (отгрузка без паллеты)": "500",
            "Комплектация": "Крышка", "Комплектация с пояснениями": "Старое описание",
            "Номенклатура прайс-листа": "Название из свойств", "Влагостойкость": "Нет"})
        self.assertEqual(row["characteristics"]["wheels"], "4")
        self.assertEqual(row["characteristics"]["support"], "На колесах")
        self.assertEqual(row["characteristics"]["equipment"], "Крышка")
        self.assertEqual(row["logistics"]["truck82_no_pallet"], "500")
        result = calculate({"1": row}, [{"product_key": 1}], {})
        for mode in ("simple", "full"):
            config = validate_config({mode + "_columns": ["name", "characteristics", "logistics"],
                                      "characteristics": ["moisture"], "logistics": ["truck82_no_pallet"]})
            ws = load_workbook(export_document(result, config, mode, "xlsx")).active
            self.assertEqual(ws["B3"].value, "Номенклатура прайс-листа")
            self.assertEqual(ws["B4"].value, "Название из свойств")
            self.assertIn("Невлагостойкий", ws["C4"].value)
            self.assertIn("500", ws["D4"].value)
            self.assertEqual(export_document(result, config, mode, "pdf").read(4), b"%PDF")

    def run_order(self, quantity, **changes):
        return calculate({"1": product(**changes)}, [{"product_key": 1, "quantity": quantity}], {})

    def test_strict_threshold_and_reprice_whole_order(self):
        self.assertEqual(self.run_order(500)["automatic_type"], "retail")
        result = self.run_order(501)
        self.assertEqual(result["automatic_type"], "small")
        self.assertEqual(result["net"], Decimal("45090.00"))
        # Reprice sequentially: retail > 300000 does not by itself imply medium.
        self.assertEqual(self.run_order(3200)["automatic_type"], "small")
        self.assertEqual(self.run_order(10000)["automatic_type"], "medium")
        self.assertEqual(self.run_order(10001)["automatic_type"], "large")

    def test_manual_types_do_not_change_recommendation(self):
        products = {"1": product(), "2": product(product_key=2)}
        items = [{"product_key": 1, "quantity": 300, "price_type": "large"}, {"product_key": 2, "quantity": 300}]
        result = calculate(products, items, {})
        self.assertEqual(result["automatic_type"], "small")
        self.assertTrue(result["manual"])
        self.assertEqual(result["net"], Decimal("48000"))
        self.assertEqual(result["gross"], Decimal("58560"))

    def test_vat_rounding_and_warning(self):
        for mode in ("none", "half_up", "floor", "ceil"):
            result = calculate({"1": product(retail="100.5")}, [{"product_key": 1, "quantity": 1}], {"rounding": mode, "vat": 0})
            self.assertEqual(result["net"], Decimal("101"))
            self.assertEqual(result["vat"], 0)
        result = self.run_order(40000)
        self.assertTrue(result["warning"])
        self.assertEqual(result["automatic_type"], "large")

    def test_missing_price_invalid_numbers_and_duplicate_rejected(self):
        for value in (None, "NaN", "Infinity", "-1"):
            with self.assertRaises(ValueError): self.run_order(1, retail=value)
        for quantity in (0, -1, "NaN", "1.5", "0.001", "1000000001"):
            with self.assertRaises(ValueError): self.run_order(quantity)
        with self.assertRaises(ValueError):
            calculate({"1": product()}, [{"product_key": 1}, {"product_key": 1}], {})
        with self.assertRaises(ValueError): validate_config({"thresholds": [50, 50, 800]})

    def test_missing_logistics_is_not_zero(self):
        result = self.run_order(100, weight_value=None)
        self.assertIsNone(result["logistics"]["weight"])
        self.assertEqual(result["logistics"]["pallets"], 2)

    def test_pallet_shares_are_summed_before_rounding(self):
        products = {str(i): product(product_key=i, pallet_value=str(capacity))
                    for i, capacity in enumerate((84, 120, 120), 1)}
        for quantities, expected in (((1, 1, 1), 1), ((84, 120, 120), 3), ((85, 120, 120), 4)):
            result = calculate(products, [{"product_key": i, "quantity": qty}
                for i, qty in enumerate(quantities, 1)], {})
            self.assertEqual(result["logistics"]["pallets"], expected)
        # Exact fractional sums must not create an extra pallet at a boundary.
        products = {str(i): product(product_key=i, pallet_value="3") for i in range(1, 7)}
        result = calculate(products, [{"product_key": i, "quantity": 1} for i in range(1, 7)], {})
        self.assertEqual(result["logistics"]["pallets"], 2)

    def test_all_price_tiers_round_before_vat_and_quantity(self):
        row = product(retail="100.50", small="90.49", medium="80.50", large="70.01")
        for tier, expected in (("retail", 101), ("small", 90), ("medium", 81), ("large", 70)):
            result = calculate({"1": row}, [{"product_key": 1, "quantity": 3, "price_type": tier}], {})
            self.assertEqual(result["rows"][0]["unit_net"], expected)
            self.assertEqual(result["net"], expected * 3)
            self.assertEqual(result["vat"], Decimal(expected * 3) * Decimal("0.22"))
        self.assertEqual(row["retail"], "100.50")

    def test_partial_logistics_keeps_known_values(self):
        products = {"1": product(weight_value=None, pallet_value=None), "2": product(product_key=2)}
        result = calculate(products, [{"product_key": 1, "quantity": 10}, {"product_key": 2, "quantity": 75}], {})
        self.assertEqual(result["logistics"], {"weight": Decimal(150), "pallets": Decimal(2)})
        self.assertEqual(result["logistics_missing"], {"weight": 1, "pallets": 1})

    def test_old_columns_and_non_default_warehouse_preferences(self):
        config = validate_config({"full_columns": ["product_key", "code"], "warehouses": ["Новый склад"]})
        self.assertEqual(config["full_columns"], ["code"])
        self.assertEqual(config["warehouses"], ["Новый склад"])

    def test_characteristics_and_logistics_mapping(self):
        row = decorate(product(color="Черный", nom_cn_fea="3923", quantity_eurotruck=600), {
            "Длина (Глубина), мм": "600", "Ширина, мм": "400", "Высота, мм": "200",
            "Объём, л": "7,5", "Объем, л": "8", "Перфорация стенок": "Нет",
            "Способ сложения (коробка)": "120", "Вес, кг": "1,5", "Складирование": "60", "Наши предложения": "Новинка", "Материал": "PP"})
        self.assertEqual(row["characteristics"]["dimensions"], "600 × 400 × 200")
        self.assertEqual(row["characteristics"]["volume"], "7,5")
        self.assertNotIn("perforation", row["characteristics"])
        self.assertEqual(row["logistics"]["packing"], "по 120 шт./короб")
        self.assertEqual(row["logistics"]["tnved"], "3923")
        self.assertEqual(row["our_offers"], "Новинка")
        self.assertEqual(row["material"], "PP")

    def test_xlsx_embeds_photo_and_does_not_execute_names(self):
        from PIL import Image
        from openpyxl import load_workbook
        image = io.BytesIO(); Image.new("RGB", (10, 10), "white").save(image, format="PNG")
        result = calculate({"1": product(name="=1+1", image="https://iplast.com/a.png")}, [{"product_key": 1}], {})
        config = validate_config({"full_columns": ["image", "name", "unit_net", "url"]})
        with patch("sales_calculator.export.image_bytes", return_value=image.getvalue()):
            document = export_document(result, config, "full", "xlsx")
        self.assertTrue(any(n.startswith("xl/media/") for n in ZipFile(document).namelist()))
        document.seek(0); ws = load_workbook(document).active
        self.assertEqual(ws["C4"].data_type, "s")
        self.assertEqual(ws["C4"].value, "=1+1")

    def test_pdf_and_simple_column_selection(self):
        result = self.run_order(1)
        config = validate_config({"simple_columns": ["name", "retail_net", "retail_gross"]})
        pdf = export_document(result, config, "simple", "pdf")
        self.assertEqual(pdf.read(4), b"%PDF")
        from openpyxl import load_workbook
        ws = load_workbook(export_document(result, config, "simple", "xlsx")).active
        self.assertEqual(ws.max_column, 4)
        self.assertIn("50 000", ws["C3"].value)

    def test_pdf_photo_only_without_available_image(self):
        document = export_document(self.run_order(1), validate_config({"simple_columns": ["image"]}), "simple", "pdf")
        self.assertEqual(document.read(4), b"%PDF")

    def test_export_article_text_and_totals(self):
        from openpyxl import load_workbook
        from .export import display
        config = validate_config({"full_columns": ["code", "name", "unit_net"]})
        result = self.run_order(1)
        ws = load_workbook(export_document(result, config, "full", "xlsx")).active
        self.assertEqual(ws.title, "Sheet")
        self.assertEqual(ws["B4"].value, "00000000123")
        self.assertEqual(ws["B4"].data_type, "s")
        self.assertEqual(ws["B4"].number_format, "@")
        self.assertEqual(ws.max_row, 7)
        self.assertEqual(display(result["rows"][0], "code", config), "00000000123")

    def test_pdf_splits_long_characteristic_across_pages(self):
        result = self.run_order(1, characteristics={"equipment": "Длинная комплектация " * 2000})
        pdf = export_document(result, validate_config({}), "full", "pdf")
        self.assertEqual(pdf.read(4), b"%PDF")

    def test_whole_prices_and_legacy_preferences_in_exports(self):
        from openpyxl import load_workbook
        from .export import price_text
        for source, expected in (("100", 100), ("100.25", 100), ("100.1234", 100), ("100.5", 101)):
            config = validate_config({"rounding": "ceil", "full_columns": ["unit_net", "unit_gross", "price_list"], "full_column_order": ["unit_net", "unit_gross", "name_1c"]})
            self.assertNotIn("rounding", config)
            self.assertEqual(config["full_columns"][-1], "name_1c")
            result = calculate({"1": product(retail=source)}, [{"product_key": 1}], config)
            self.assertEqual(result["rows"][0]["unit_net"], expected)
            ws = load_workbook(export_document(result, config, "full", "xlsx")).active
            self.assertEqual(ws["B4"].value, expected)
            self.assertEqual(ws["D4"].value, product()["name_1c"])
            self.assertEqual(ws["B4"].alignment.horizontal, "right")
            self.assertEqual(ws["B3"].alignment.horizontal, "center")
            self.assertEqual(price_text(result["rows"][0]["unit_net"]), str(expected))
            self.assertNotIn(chr(8381), ws["B3"].value)
            self.assertEqual(ws["B4"].number_format, '#,##0')
            self.assertEqual(ws["D5"].number_format, '#,##0')


class PublicationTests(UnitTestCase):
    def publish_with_client(self, client, rows=None):
        from .warehouse import publish
        with patch("django.db.transaction.atomic"), patch("sales_calculator.warehouse.connection"), patch("sales_calculator.warehouse.build_rows", return_value=rows or []), patch("sales_calculator.warehouse.get_clickhouse_client", return_value=client):
            return publish(date(2026, 9, 30), False)

    def test_insert_has_named_metadata_and_unavailable_stock_before_exchange(self):
        import json
        from .warehouse import COLUMNS
        client = Mock()
        row = product(distr=None, distr_1=None, stocks=None, quantity_eurotruck=240)
        self.assertEqual(self.publish_with_client(client, [row]), 1)
        calls = client.execute.call_args_list
        insert_index = next(i for i, call in enumerate(calls) if call.args[0].startswith("INSERT"))
        values = calls[insert_index].args[1][0]
        self.assertEqual(len(values), len(COLUMNS.split(", ")))
        inserted = dict(zip(COLUMNS.split(", "), values))
        self.assertEqual(inserted["name"], row["name"])
        self.assertEqual(inserted["quantity_eurotruck"], Decimal(240))
        self.assertIsNone(json.loads(inserted["stocks"]))
        self.assertTrue(calls[insert_index + 1].args[0].startswith("EXCHANGE"))

    def test_swap_failure_preserves_original_error_and_cleans_staging(self):
        client = Mock()
        def execute(sql):
            if sql.startswith("EXCHANGE"):
                raise RuntimeError("exchange failed")
        client.execute.side_effect = execute
        with self.assertRaisesRegex(RuntimeError, "exchange failed"):
            self.publish_with_client(client)
        self.assertTrue(client.execute.call_args.args[0].startswith("DROP TABLE IF EXISTS default.sales_calculator_product_build_"))

    def test_cleanup_failure_does_not_report_successful_publication_as_failed(self):
        client = Mock()
        def execute(sql):
            if sql.startswith("DROP"):
                raise RuntimeError("cleanup failed")
        client.execute.side_effect = execute
        self.assertEqual(self.publish_with_client(client), 0)


class AccessTests(TestCase):
    def test_export_comparison_flag_uses_same_calculation_as_screen(self):
        from .api import ExportView, ComparisonView
        products = [product(region="Main"), product(region="Other", retail="200")]
        def read(region=None):
            return [p for p in products if region is None or p["region"] == region]
        for comparing in (False, True):
            with patch("sales_calculator.api.read_products", side_effect=read), patch("sales_calculator.export.export_document", return_value=io.BytesIO(b"document")) as export:
                request = {"items": [{"product_key": 1}], "region": "Main", "mode": "simple", "format": "xlsx", "comparing": comparing}
                response = self.request("post", ExportView, data=request)
                self.assertEqual(response.status_code, 200)
                result = export.call_args.args[0]
                self.assertEqual("warehouses" in result, comparing)
                if comparing:
                    from .api import serializable
                    screen = self.request("post", ComparisonView, data={"items": request["items"]})
                    self.assertEqual(serializable(result["warehouses"]), screen.data["warehouses"])
                response.close()

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="viewer")
        self.other = get_user_model().objects.create_user(username="other")
        from organizations.models import Organization, OrganizationMembership
        organization = Organization.objects.get(code="iplast")
        for user in (self.user, self.other):
            OrganizationMembership.objects.create(user=user, organization=organization, is_default=True)
        self.dashboard, _ = Dashboard.objects.get_or_create(organization=organization, slug="commercial-price", defaults={"name": "Commercial Price"})
        DashboardAccess.objects.create(user=self.user, dashboard=self.dashboard, can_view=True, can_edit=False)
        self.factory = APIRequestFactory()

    def request(self, method, view, user=None, data=None):
        request = getattr(self.factory, method)("/", data=data or {}, format="json")
        force_authenticate(request, user=user or self.user)
        return view.as_view()(request)

    def test_viewer_can_save_own_settings_and_refresh(self):
        self.assertEqual(self.request("put", SettingsView, data={"vat": 0}).status_code, 200)
        self.assertEqual(self.request("get", SettingsView).data["config"]["vat"], 0)
        with patch("sales_calculator.api.request_refresh", return_value=True) as refresh, patch("sales_calculator.api.state_payload", return_value={}):
            self.assertEqual(self.request("post", RefreshView).status_code, 202)
            refresh.assert_called_once_with(sources=True)
        DashboardAccess.objects.create(user=self.other, dashboard=self.dashboard, can_view=True)
        self.assertEqual(self.request("get", SettingsView, user=self.other).data["config"]["vat"], 22)

    def test_no_access_cannot_read_products_or_settings(self):
        self.assertEqual(self.request("get", SettingsView, user=self.other).status_code, 403)
        with patch("sales_calculator.api.read_products") as read:
            self.assertEqual(self.request("get", ProductsView, user=self.other).status_code, 403)
            read.assert_not_called()
        with patch("sales_calculator.api.request_refresh") as refresh:
            self.assertEqual(self.request("post", RefreshView, user=self.other).status_code, 403)
            refresh.assert_not_called()

    def test_calculator_visibility_is_limited_to_superusers(self):
        for username, superuser, expected in (("viewer", False, False), ("analyst", False, False), ("Analyst", False, False), ("admin", True, True)):
            with self.subTest(username=username):
                self.user.username = username
                self.user.is_superuser = superuser
                self.user.save()
                self.assertEqual(self.request("get", SettingsView).data["can_use_calculator"], expected)

    def test_reset_restores_all_defaults_but_keeps_shipping_region(self):
        self.request("put", SettingsView, data={"region": "Москва", "vat": 0, "simple_columns": ["quantity"], "full_columns": [], "characteristics": [], "warehouses": []})
        response = self.request("post", SettingsView)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, validate_config({"region": "Москва"}))
        self.assertEqual(self.request("get", SettingsView).data["config"], response.data)
        response = self.request("post", SettingsView, data={"region": "Санкт-Петербург"})
        self.assertEqual(response.data, validate_config({"region": "Санкт-Петербург"}))
        self.assertEqual(self.request("post", SettingsView, user=self.other).status_code, 403)

    def test_comparison_uses_each_warehouse_prices_and_current_vat(self):
        from .api import ComparisonView
        products = [product(region="Москва", retail="100.5"), product(region="СПб", retail="80"), product(product_key=2, region="Казань")]
        with patch("sales_calculator.api.read_products", return_value=products) as read:
            response = self.request("post", ComparisonView, data={"items": [{"product_key": 1, "quantity": 2}]})
        self.assertEqual(response.status_code, 200)
        read.assert_called_once_with()
        warehouses = {row["region"]: row["rows"] for row in response.data["warehouses"]}
        self.assertEqual(warehouses["Москва"][0]["retail_net"], "101")
        self.assertEqual(warehouses["Москва"][0]["retail_gross"], "123.22")
        self.assertEqual(warehouses["СПб"][0]["retail_gross"], "97.60")
        self.assertEqual(warehouses["Казань"], [])
        self.request("put", SettingsView, data={"vat": 0})
        with patch("sales_calculator.api.read_products", return_value=products):
            response = self.request("post", ComparisonView, data={"items": [{"product_key": 1}]})
        self.assertEqual(response.data["warehouses"][1]["rows"][0]["retail_gross"], "101.00")

    def test_comparison_rejects_invalid_items_and_unauthorized_access(self):
        from .api import ComparisonView
        with patch("sales_calculator.api.read_products", return_value=[product()]):
            for items in ("invalid", [{"product_key": 1}, {"product_key": 1}], [{}], [{"product_key": 1, "quantity": 0}]):
                self.assertEqual(self.request("post", ComparisonView, data={"items": items}).status_code, 400)
        with patch("sales_calculator.api.read_products") as read:
            self.assertEqual(self.request("post", ComparisonView, user=self.other).status_code, 403)
            read.assert_not_called()

    def test_viewer_sees_refresh_button_and_duplicate_refresh_is_rejected(self):
        with patch("sales_calculator.api.read_products", return_value=[]), patch("sales_calculator.api.state_payload", return_value={}):
            self.assertTrue(self.request("get", ProductsView).data["can_refresh"])
        with patch("sales_calculator.api.request_refresh", return_value=False) as refresh, patch("sales_calculator.api.state_payload", return_value={"running": True}):
            response = self.request("post", RefreshView)
            self.assertEqual(response.status_code, 409)
            self.assertTrue(response.data["running"])
            refresh.assert_called_once_with(sources=True)

    def test_settings_list_all_warehouses_but_select_defaults(self):
        from datasets.models import NomenclatureStock
        with patch.object(NomenclatureStock.objects, "exclude") as query:
            query.return_value.exclude.return_value.values_list.return_value.distinct.return_value = ["Новый склад"]
            response = self.request("get", SettingsView)
        self.assertIn("Новый склад", response.data["warehouses"])
        self.assertNotIn("Новый склад", response.data["config"]["warehouses"])

    def test_pdf_response_filename_and_content(self):
        from .api import ExportView
        with patch("sales_calculator.api.read_products", return_value=[product()]):
            response = self.request("post", ExportView, data={"items": [{"product_key": 1}], "region": "Москва", "mode": "simple", "format": "pdf"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("%D0%9F%D1%80%D0%B0%D0%B9%D1%81.pdf", response["Content-Disposition"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))
        response.close()

    def test_old_stock_hidden(self):
        with patch("sales_calculator.api.read_products", return_value=[product(calculation_date="2000-01-01", stocks={"A": 7})]), patch("sales_calculator.api.state_payload", return_value={}):
            response = self.request("get", ProductsView)
        self.assertTrue(response.data["stale"])
        self.assertIsNone(response.data["products"][0]["stocks"])


class RefreshTests(TestCase):
    def test_price_failure_preserves_mart_and_skips_stock(self):
        from .refresh import drain
        SalesCalculatorRefresh.objects.create(pk=1, requested=True, refresh_sources=True)
        cursor = Mock(); cursor.fetchone.return_value = [True]
        with patch("sales_calculator.refresh.connection") as conn, patch("datasets.services.external_api.price_api_loader.load_prices_from_api", side_effect=RuntimeError("1C unavailable")), patch("datasets.services.external_api.stock_api_loader.load_stocks_from_api") as stock, patch("sales_calculator.warehouse.publish") as publish:
            conn.cursor.return_value.__enter__.return_value = cursor
            drain()
        stock.assert_not_called(); publish.assert_not_called()
        self.assertEqual(SalesCalculatorRefresh.objects.get(pk=1).status, "failed")

    def test_stock_failure_publishes_without_stock(self):
        from .refresh import drain
        SalesCalculatorRefresh.objects.create(pk=1, requested=True, refresh_sources=True)
        cursor = Mock(); cursor.fetchone.return_value = [True]
        with patch("sales_calculator.refresh.connection") as conn, patch("datasets.services.external_api.price_api_loader.load_prices_from_api"), patch("datasets.services.external_api.stock_api_loader.load_stocks_from_api", side_effect=RuntimeError("stock unavailable")), patch("datasets.models.NomenclaturePrice.objects.filter") as price, patch("datasets.models.NomenclatureStock.objects.filter") as stock, patch("sales_calculator.warehouse.publish", return_value=5) as publish:
            conn.cursor.return_value.__enter__.return_value = cursor
            price.return_value.exists.return_value = True; stock.return_value.exists.return_value = True
            drain()
        publish.assert_called_once_with(timezone.localdate(), False)
        state = SalesCalculatorRefresh.objects.get(pk=1)
        self.assertEqual(state.status, "success")
        self.assertFalse(state.stock_available)
        self.assertIsNotNone(state.stock_failed_at)

    def test_concurrent_worker_does_not_consume_request(self):
        from .refresh import drain
        SalesCalculatorRefresh.objects.create(pk=1, requested=True)
        cursor = Mock(); cursor.fetchone.return_value = [False]
        with patch("sales_calculator.refresh.connection") as conn, patch("sales_calculator.warehouse.publish") as publish:
            conn.cursor.return_value.__enter__.return_value = cursor
            drain()
        publish.assert_not_called()
        self.assertTrue(SalesCalculatorRefresh.objects.get(pk=1).requested)

    def test_request_during_publication_is_processed_before_unlock(self):
        from .refresh import drain
        SalesCalculatorRefresh.objects.create(pk=1, requested=True)
        cursor = Mock(); cursor.fetchone.return_value = [True]
        calls = []
        def publish(*args):
            calls.append(args)
            if len(calls) == 1:
                SalesCalculatorRefresh.objects.filter(pk=1).update(requested=True)
            return 2
        with patch("sales_calculator.refresh.connection") as conn, patch("datasets.models.NomenclaturePrice.objects.filter") as price, patch("datasets.models.NomenclatureStock.objects.filter") as stock, patch("sales_calculator.warehouse.publish", side_effect=publish):
            conn.cursor.return_value.__enter__.return_value = cursor
            price.return_value.exists.return_value = True
            stock.return_value.exists.return_value = True
            drain()
        self.assertEqual(len(calls), 2)
        self.assertEqual(sum("pg_advisory_unlock" in str(call) for call in cursor.execute.call_args_list), 1)
        self.assertFalse(SalesCalculatorRefresh.objects.get(pk=1).requested)
