"""Printable, tabular layouts shared by price lists and commercial offers."""
import io
import math
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape
from urllib.parse import urlsplit

from django.utils import timezone

from .export import display, price_text, NUMERIC_COLUMNS


def heading(result, mode):
    title = "ПРАЙС-ЛИСТ" if mode == "simple" else "КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ"
    return f'ООО "Ай-Пласт" • {title} • {timezone.localdate():%d.%m.%Y} • СКЛАД ОТГРУЗКИ: {result["rows"][0]["region"].upper()}'


def width(key):
    if key == "row_number":
        return 7
    return 40 if key in ("name", "name_1c", "characteristics", "logistics") else 18


def xlsx(result, config, mode, labels, columns, images):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.drawing.image import Image
    from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.utils import get_column_letter
    from openpyxl.utils.units import pixels_to_EMU
    wb = Workbook()
    ws = wb.active
    ws.sheet_view.showGridLines = False
    last = len(columns)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last)
    ws.cell(1, 1, heading(result, mode))
    header_lines = math.ceil(len(heading(result, mode)) / max(12, sum(width(key) for key in columns) * .8))
    ws.row_dimensions[1].height = max(45, header_lines * 18 + 16)
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="DC2F2F")
    ws["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for index, key in enumerate(columns, 1):
        ws.column_dimensions[get_column_letter(index)].width = width(key)
    def add_image(data, row, column, max_width, max_height, center=True):
        image = Image(io.BytesIO(data))
        scale = min(max_width / image.width, max_height / image.height)
        image.width, image.height = image.width * scale, image.height * scale
        dx = 6 + ((max_width - image.width) / 2 if center else 0)
        dy = 6 + ((max_height - image.height) / 2 if center else 0)
        image.anchor = OneCellAnchor(_from=AnchorMarker(col=column - 1, row=row - 1, colOff=pixels_to_EMU(dx), rowOff=pixels_to_EMU(dy)), ext=XDRPositiveSize2D(pixels_to_EMU(image.width), pixels_to_EMU(image.height)))
        ws.add_image(image)
    ws.append([])
    for index, key in enumerate(columns, 1):
        ws.cell(3, index, labels[key])
    line = Side(style="thin", color="E5E8E1")
    for cell in ws[3]:
        cell.font = Font(name="Arial", size=10, bold=True, color="454C40")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=line, right=line, top=line, bottom=line)
    if "image" in columns:
        ws.cell(3, columns.index("image") + 1).alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
    ws.row_dimensions[3].height = 65
    for index, row in enumerate(result["rows"], 4):
        lines = max((sum(max(1, math.ceil(len(part) / max(8, width(key) - 3))) for part in str(display(row, key, config)).split("\n")) for key in columns if key != "image"), default=1)
        height = min(409, max(80, lines * 15 + 12))
        ws.row_dimensions[index].height = height
        for column, key in enumerate(columns, 1):
            cell = ws.cell(index, column)
            value = display(row, key, config)
            cell.font = Font(name="Arial", size=10, color="242722")
            cell.border = Border(left=line, right=line, bottom=line)
            cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="right" if key in NUMERIC_COLUMNS else "left")
            if key == "image":
                data = images.get(row.get("image"))
                if data:
                    add_image(data, index, column, width(key) * 7 - 12, height * 96 / 72 - 12)
                else:
                    cell.value = "Изображение недоступно"
                continue
            cell.value = value
            if isinstance(value, str):
                cell.data_type = "s"
                if key == "code":
                    cell.number_format = "@"
            else:
                digits = max(0, -Decimal(str(value)).normalize().as_tuple().exponent)
                cell.number_format = '#,##0' + ('.' + '0' * digits if digits else '')
            if key == "url" and urlsplit(row.get("url") or "").scheme in ("http", "https"):
                cell.hyperlink = row["url"]
                cell.font = Font(name="Arial", size=10, color="385C36", underline="single")
    end = len(result["rows"]) + 3
    if mode == "full":
        for index, (label, key) in enumerate((("Итого сумма руб. без НДС:", "net"), ("НДС:", "vat"), ("Итого сумма руб. с НДС:", "gross")), end + 1):
            if last > 1:
                ws.merge_cells(start_row=index, start_column=1, end_row=index, end_column=last - 1)
                ws.cell(index, 1, label)
                ws.cell(index, last, result[key]).number_format = '#,##0.00'
            else:
                ws.cell(index, 1, f"{label} {price_text(result[key])}")
            for cell in ws[index]:
                cell.font = Font(name="Arial", size=11, bold=True)
                cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
            ws.row_dimensions[index].height = 32
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:{get_column_letter(last)}{end}"
    ws.print_title_rows = "1:3"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def pdf(result, config, mode, labels, columns, images):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image, KeepTogether
    font = next((p for p in [Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('C:/Windows/Fonts/arial.ttf')] if p.exists()), None)
    if font is None:
        raise ValueError("Не установлен шрифт для PDF")
    if 'CommercialPrice' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CommercialPrice', str(font)))
    bold_font = font.with_name('DejaVuSans-Bold.ttf' if font.name == 'DejaVuSans.ttf' else 'arialbd.ttf')
    if 'CommercialPriceBold' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CommercialPriceBold', str(bold_font)))
    style = ParagraphStyle('Body', fontName='CommercialPrice', fontSize=8, leading=11, textColor=colors.HexColor('#242722'))
    numeric = ParagraphStyle('Numeric', parent=style, alignment=2)
    total_numeric = ParagraphStyle('TotalNumeric', parent=numeric, fontName='CommercialPriceBold')
    header = ParagraphStyle('Header', parent=style, alignment=1)
    brand = ParagraphStyle('Brand', parent=style, fontSize=12, leading=17, textColor=colors.white, alignment=1)
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A3), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    brand_cells = [Paragraph(escape(heading(result, mode)), brand)]
    brand_widths = [doc.width]
    banner = Table([brand_cells], colWidths=brand_widths)
    banner.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#dc2f2f')), ('VALIGN',(0,0),(-1,-1),'MIDDLE'), ('TOPPADDING',(0,0),(-1,-1),12), ('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    widths = [doc.width * width(key) / sum(width(k) for k in columns) for key in columns]
    if "image" in columns:
        image_index = columns.index("image")
        minimum = pdfmetrics.stringWidth(labels["image"], header.fontName, header.fontSize) + 16
        if widths[image_index] < minimum:
            remaining = doc.width - widths[image_index]
            widths = [minimum if index == image_index else value * (doc.width - minimum) / remaining for index, value in enumerate(widths)]
    cells = [[Paragraph(escape(labels[key]).replace('\n', '<br/>'), header) for key in columns]]
    for row in result['rows']:
        values = []
        row_height = 64
        for key, col_width in zip(columns, widths):
            value = display(row, key, config)
            if key == 'image':
                values.append(None)
                continue
            if key in NUMERIC_COLUMNS - {'code'} and value != '':
                value = price_text(value)
            text = escape(str(value)).replace('\n', '<br/>')
            if key == 'url' and urlsplit(row.get('url') or '').scheme in ('https', 'http'):
                text = f'<link href="{escape(row["url"], {chr(34): "&quot;"})}">{text}</link>'
            paragraph = Paragraph(text, numeric if key in NUMERIC_COLUMNS else style)
            row_height = max(row_height, paragraph.wrap(max(1, col_width - 12), 100000)[1])
            values.append(paragraph)
        for i, key in enumerate(columns):
            if key == 'image':
                data = images.get(row.get('image'))
                if data:
                    image = Image(io.BytesIO(data))
                    scale = min((widths[i] - 12) / image.imageWidth, min(row_height, 500) / image.imageHeight)
                    image.drawWidth, image.drawHeight = image.imageWidth * scale, image.imageHeight * scale
                    values[i] = image
                else:
                    values[i] = Paragraph('Изображение недоступно', style)
        cells.append(values)
    table = Table(cells, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.HexColor('#e5e8e1')), ('VALIGN',(0,0),(-1,-1),'MIDDLE'), ('TOPPADDING',(0,0),(-1,-1),8), ('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    flow = [banner, Spacer(1, 12), table]
    if mode == 'full':
        totals = Table([
            [Paragraph('Итого сумма руб. без НДС:', total_numeric), Paragraph(f'{result["net"]:,.2f}'.replace(',', ' ').replace('.', ','), total_numeric)],
            [Paragraph('НДС:', total_numeric), Paragraph(f'{result["vat"]:,.2f}'.replace(',', ' ').replace('.', ','), total_numeric)],
            [Paragraph('Итого сумма руб. с НДС:', total_numeric), Paragraph(f'{result["gross"]:,.2f}'.replace(',', ' ').replace('.', ','), total_numeric)],
        ], colWidths=[220, 110], hAlign='RIGHT')
        totals.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8)]))
        flow.append(KeepTogether([Spacer(1, 12), totals]))
    doc.build(flow)
    output.seek(0)
    return output
