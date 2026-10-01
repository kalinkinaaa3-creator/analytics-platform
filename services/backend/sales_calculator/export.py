import hashlib
import io
import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import requests
from django.conf import settings
from django.utils import timezone

from .configuration import CHARACTERISTICS, LOGISTICS, FULL_COLUMNS, SIMPLE_COLUMNS, PRICE_LABELS

logger = logging.getLogger("sales_calculator")
PRICE_COLUMNS = {"unit_net", "unit_gross", *[f"{tier}_{tax}" for tier in PRICE_LABELS for tax in ("net", "gross")]}


def price_text(value, config):
    digits = 2 if config["rounding"] == "none" else 0
    value = Decimal(str(value)).quantize(Decimal("0.01") if digits else Decimal(1), rounding=ROUND_HALF_UP)
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


def display(row, key, config):
    if key == "code":
        return str(row.get("code") or "").zfill(11) if row.get("code") is not None else ""
    if key in ("characteristics", "logistics"):
        labels = CHARACTERISTICS if key == "characteristics" else LOGISTICS
        return "\n".join(f"{labels[k]}: {row.get(key, {}).get(k)}" for k in config[key] if row.get(key, {}).get(k) not in (None, ""))
    if key == "price_type":
        return PRICE_LABELS[row[key]]
    if key == "url":
        return "Посмотреть на сайте" if row.get(key) else ""
    value = row.get(key)
    return "" if value is None else value


def export_document(result, config, mode, kind):
    labels = dict(FULL_COLUMNS if mode == "full" else SIMPLE_COLUMNS)
    if mode == "simple":
        bounds = ["0", *config["thresholds"]]
        for index, (tier, label) in enumerate(PRICE_LABELS.items()):
            band = f"{bounds[index]}–{bounds[index + 1]} ₽" if index < 3 else f"свыше {bounds[index]} ₽"
            for tax in ("net", "gross"):
                labels[f"{tier}_{tax}"] = f"{label} ({band}), {'без НДС' if tax == 'net' else 'с НДС'}"
    columns = config[mode + "_columns"]
    if not columns:
        raise ValueError("Выберите столбцы для выгрузки")
    # Shared columns and data are used by both formats.
    from concurrent.futures import ThreadPoolExecutor
    urls = list(dict.fromkeys(r.get("image") for r in result["rows"] if r.get("image"))) if "image" in columns else []
    with ThreadPoolExecutor(max_workers=4) as executor:
        images = dict(zip(urls, executor.map(image_bytes, urls)))
    if kind == "xlsx":
        return _xlsx(result, config, mode, labels, columns, images)
    return _pdf(result, config, mode, labels, columns, images)


def _xlsx(result, config, mode, labels, columns, images):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.drawing.image import Image
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    title = "Прайс" if mode == "simple" else "Предложение"
    ws.title = title
    ws.append([title])
    ws.append([f"{timezone.localdate():%d.%m.%Y} · Регион: {result['rows'][0]['region']} · НДС {config['vat']}%"])
    ws.append([labels[k] for k in columns])
    for cell in ws[3]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="4F6347")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for index, row in enumerate(result["rows"], 4):
        for column, key in enumerate(columns, 1):
            cell = ws.cell(index, column)
            value = display(row, key, config)
            if key == "image":
                data = images.get(row.get("image"))
                if data:
                    image = Image(io.BytesIO(data))
                    scale = min(95 / image.width, 70 / image.height)
                    image.width, image.height = image.width * scale, image.height * scale
                    ws.add_image(image, cell.coordinate)
                else:
                    cell.value = "Фото недоступно"
            else:
                cell.value = value
                if isinstance(value, str):
                    cell.data_type = "s"  # Untrusted supplier names must not become Excel formulas.
                    if key == "code":
                        cell.number_format = "@"
                else:
                    cell.number_format = '#,##0' if key in PRICE_COLUMNS and config["rounding"] != "none" else '#,##0.00'
                if key == "url" and urlsplit(row.get("url") or "").scheme in ("http", "https"):
                    cell.hyperlink = row["url"]
                    cell.font = Font(color="385C36", underline="single")
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            if index % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F3F6F1")
        ws.row_dimensions[index].height = max(80, 14 * max((str(display(row, k, config)).count("\n") + 1 for k in columns if k != "image"), default=1))
    for index, key in enumerate(columns, 1):
        ws.column_dimensions[get_column_letter(index)].width = 45 if key in ("characteristics", "logistics", "name", "price_list") else 19
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:{get_column_letter(len(columns))}{len(result['rows'])+3}"
    ws.print_title_rows = "1:3"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    output = io.BytesIO(); wb.save(output); output.seek(0)
    return output


def _pdf(result, config, mode, labels, columns, images):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
    font = next((p for p in [Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('C:/Windows/Fonts/arial.ttf')] if p.exists()), None)
    if font is None:
        raise ValueError("Не установлен шрифт для PDF")
    if 'CommercialPrice' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CommercialPrice', str(font)))
    style = ParagraphStyle('Body', fontName='CommercialPrice', fontSize=8, leading=11)
    title = ParagraphStyle('Title', parent=style, fontSize=18, leading=24, spaceAfter=12)
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=25, rightMargin=25, topMargin=25, bottomMargin=25)
    flow = [Paragraph('Прайс' if mode == 'simple' else 'Предложение', title), Paragraph(escape(f"Регион: {result['rows'][0]['region']} · НДС {config['vat']}% · {timezone.localdate():%d.%m.%Y}"), style), Spacer(1, 12)]
    # Compact product blocks remain readable even when many optional columns are enabled.
    for row in result['rows']:
        cells = []
        for key in columns:
            if key == 'image':
                data = images.get(row.get('image'))
                if data:
                    photo = Image(io.BytesIO(data))
                    scale = min(90 / photo.imageWidth, 65 / photo.imageHeight)
                    photo.drawWidth, photo.drawHeight = photo.imageWidth * scale, photo.imageHeight * scale
                    cells.append([Paragraph(labels[key], style), photo])
                else:
                    cells.append([Paragraph(labels[key], style), Paragraph("Фото недоступно", style)])
                continue
            value = display(row, key, config)
            if key in PRICE_COLUMNS and value != "":
                value = price_text(value, config)
            text = escape(str(value)).replace('\n', '<br/>')
            if key == 'url' and urlsplit(row.get('url') or '').scheme in ('https', 'http'):
                text = f'<link href="{escape(row["url"], {chr(34): "&quot;"})}">{text}</link>'
            cells.append([Paragraph(escape(labels[key]), style), Paragraph(text, style)])
        # A single long characteristic must also be splittable across pages.
        table = Table(cells, colWidths=[160, doc.width - 172], hAlign='LEFT', splitByRow=1, splitInRow=1)
        table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F3F6F1')), ('VALIGN',(0,0),(-1,-1),'TOP'), ('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        flow.extend([table, Spacer(1,12)])
    doc.build(flow); output.seek(0)
    return output
