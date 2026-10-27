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
        own_codes = dict(models.ParserProductUrl.objects.filter(source='base').exclude(own_code__isnull=True).exclude(own_code='').values_list('pk', 'own_code'))
        report = health_report(page_size=None)
        sheet('Проверка данных', ['Раздел', 'Уровень', 'Код проверки', 'Наименование', 'Регион', 'Замечание', 'Исправление', 'Код 1С'],
              ([item[key] for key in ('section', 'severity', 'code', 'nom', 'region', 'message', 'fix', 'code_1c')] for item in report['results']))
        sheet('Срезы', ['Источник', 'Дата'], [('Прайс', report['price_date']), ('Расчёт', (report['snapshot'] or {}).get('date'))])
        from .iprice_models import IPriceRegionalInput, IPriceSourceImport
        from openpyxl import load_workbook
        sheet('Действующая классификация',
              ['Ключ товара', 'Тип', 'Категория', 'Подкатегория', 'Материал', 'Цвет', 'Модификация', 'Группа аналогов', 'Тип товара', 'Ссылка', 'Код 1С'],
              ([r.product_key, r.category, r.subcategory, r.subcategory_type, r.material, r.color, r.modification,
                r.article_number_analogs, r.get_item_type_display(), r.url, own_codes.get(r.product_key)]
               for r in models.ParserProductClassification.objects.filter(status='active').order_by('product_key').iterator()))
        sheet('Действующие аналоги', ['Ключ нашего товара', 'Ключ конкурента', 'Способ добавления', 'Код 1С'],
              ([r.product_key_base, r.product_key_competitor, r.get_match_type_display(), own_codes.get(r.product_key_base)]
               for r in models.ParserProductMatch.objects.filter(status='active').order_by('product_key_base', 'product_key_competitor').iterator()))
        sheet('Решения по учёту аналогов', ['Ключ нашего товара', 'Ключ конкурента', 'Участие в расчёте', 'Причина', 'Код 1С'],
              ([r.product_key_base, r.product_key_competitor, r.get_selection_mode_display(), r.reason, own_codes.get(r.product_key_base)]
               for r in models.IPriceCompetitorSelectionOverride.objects.order_by('product_key_base', 'product_key_competitor').iterator()))
        sheet('Действующие префиксы', ['Конкурент', 'Префикс', 'Регион'],
              models.ParserPrefix.objects.order_by('source', 'prefix').values_list('source', 'prefix', 'shipp_region').iterator())
        latest_input = IPriceRegionalInput.objects.filter(code=OuterRef('code'), region=OuterRef('region')).order_by('-month', '-pk').values('pk')[:1]
        current_inputs = IPriceRegionalInput.objects.filter(pk=Subquery(latest_input))
        sheet('Настройки расчёта', ['Последний месяц настройки', 'Регион', 'Коэффициент по рынку', 'Маржа по себестоимости, доля',
              'Минимальная маржа, доля', 'Скидка мелкого опта, доля', 'Скидка среднего опта, доля', 'Скидка крупного опта, доля',
              'Учитывать доставку', 'Доставка на единицу без НДС, руб.', 'Код 1С'],
              ([r.month, r.region, r.base_analog, r.base_exclusive, r.minimum_margin, r.small, r.medium, r.large,
                'Да' if r.include_transport else 'Нет', r.logistics_unit, r.code]
               for r in current_inputs.order_by('code', 'region').iterator()))
        last_cost = IPriceSourceImport.objects.filter(kind='product_cost').order_by('-id').first()
        cost_rows = []
        if last_cost:
            source = load_workbook(BytesIO(bytes(last_cost.content)), read_only=True, data_only=False)
            try:
                cost_rows = list(source.active.iter_rows(min_row=2, values_only=True))
            finally:
                source.close()
        sheet('Последние закупочные цены', ['Дата', 'Наименование', 'Регион', 'Закупочная цена без НДС, руб.', 'Код 1С'], ([r[0], *r[2:5], r[1]] for r in cost_rows))
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()
