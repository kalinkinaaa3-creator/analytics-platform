"""Read-only review workbooks for the Select Market sources, never legacy tables."""
from io import BytesIO

from django.db.models import F, OuterRef, Subquery
from django.db.models.functions import TruncDate
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

from . import iprice_domain_models as models
from .iprice_health import health_report


def review_workbook(kind):
    book = Workbook(write_only=True)

    def sheet(title, headers, rows):
        ws = book.create_sheet(title)
        ws.freeze_panes = 'A2'
        cells = []
        for label in headers:
            cell = WriteOnlyCell(ws, value=label)
            cell.font = Font(bold=True)
            cells.append(cell)
        ws.append(cells)
        for row in rows:
            cells = []
            for value in row:
                # Force imported strings to text, including formula-like names/codes.
                cell = WriteOnlyCell(ws, value=value)
                if isinstance(value, str):
                    cell.data_type = 's'
                cells.append(cell)
            ws.append(cells)

    if kind == 'parser_products':
        sheet('URL', ['Источник', 'ID', 'URL', 'Статус', 'Ошибка', 'Код 1С', 'В прайсе', 'На сайте'],
              models.ParserProductUrl.objects.order_by('pk').values_list('source', 'pk', 'url', 'status', 'last_error', 'own_code', 'in_price', 'on_website').iterator())
        for source, model in [('ТАРА', models.TaraProductPrice), ('Пластик Система', models.PsProductPrice), ('ТопТара', models.TtProductPrice)]:
            latest = model.objects.filter(product_key=OuterRef('product_key')).annotate(day=TruncDate('date_add')).order_by('-date_add').values('day')[:1]
            rows = model.objects.annotate(latest_date=Subquery(latest), day=TruncDate('date_add')).filter(day=F('latest_date')).order_by('product_key', 'pk')
            sheet(source, ['ID товара', 'Наименование', 'URL', 'Цена без НДС'], rows.values_list('product_key', 'name', 'url', 'final_price').iterator())
    else:
        report = health_report(page_size=None)
        sheet('Проверка данных', ['Раздел', 'Уровень', 'Код проверки', 'Код 1С', 'Наименование', 'Регион', 'Замечание', 'Исправление'],
              ([item[key] for key in ('section', 'severity', 'code', 'code_1c', 'nom', 'region', 'message', 'fix')] for item in report['results']))
        sheet('Срезы', ['Источник', 'Дата'], [('Прайс', report['price_date']), ('Расчёт', (report['snapshot'] or {}).get('date'))])
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()
