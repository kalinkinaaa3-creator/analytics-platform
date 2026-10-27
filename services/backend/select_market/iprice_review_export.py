"""Read-only review workbooks for the Select Market sources, never legacy tables."""
from io import BytesIO

from django.db.models import F, OuterRef, Subquery
from django.db.models.functions import TruncDate
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

from . import iprice_domain_models as models
from .iprice_health import health_report

SOURCE_LABELS = {'tara': 'Тара', 'tt': 'Топаз', 'ps': 'Пластик Систем', 'base': 'Селект Маркет'}


def parser_sheets(sheet):
    from collections import defaultdict
    from django.utils import timezone
    classified = set(models.ParserProductClassification.objects.filter(status='active').values_list('product_key', flat=True))
    matches = list(models.ParserProductMatch.objects.filter(status='active').values_list('product_key_base', 'product_key_competitor'))
    matched_base = {base for base, _ in matches}
    matched_competitors = {competitor for _, competitor in matches}
    url_labels = {'id': 'Ключ товара', 'source': 'Источник', 'prefix': 'Префикс', 'url': 'Ссылка на товар',
        'own_code': 'Код 1С', 'in_price': 'В прайсе', 'on_website': 'На сайте', 'additional_property': 'Дополнительное свойство',
        'status': 'Статус', 'lastmod': 'Дата изменения на сайте', 'is_loaded': 'Данные загружены',
        'last_error': 'Ошибка загрузки', 'date_add': 'Дата добавления ссылки', 'date_update': 'Дата обновления ссылки'}
    for source, model in [('tara', models.TaraProductPrice), ('tt', models.TtProductPrice),
                          ('ps', models.PsProductPrice), ('base', models.BaseProductPrice)]:
        urls = models.ParserProductUrl.objects.filter(source=source).order_by('pk')
        keys = urls.values('pk')
        url_fields = [field.name for field in models.ParserProductUrl._meta.fields
                      if source == 'base' or field.name not in ('own_code', 'in_price', 'on_website')]
        price_fields = [field for field in model._meta.fields if field.name != 'product_key']
        price_labels = {'id': 'Ключ записи цены', 'date_add': 'Дата сбора цены', 'code_1c': 'Код 1С из цены', 'url': 'Ссылка на цену'}
        latest = model.objects.filter(product_key=OuterRef('product_key')).annotate(day=TruncDate('date_add')).order_by('-date_add', '-pk').values('day')[:1]
        prices = defaultdict(list)
        for row in model.objects.filter(product_key__in=keys).annotate(day=TruncDate('date_add'), latest=Subquery(latest)).filter(day=F('latest')).order_by('pk'):
            prices[row.product_key].append(row)
        properties = defaultdict(dict)
        property_days = {}
        for row in models.ParserProductProperty.objects.filter(source=source, product_key__in=keys).exclude(properties__isnull=True).exclude(properties='').order_by('-date_add', '-pk'):
            identity = (row.product_key, row.properties)
            day = timezone.localtime(row.date_add).date()
            property_days.setdefault(identity, day)
            if property_days[identity] != day:
                continue
            values = properties[row.product_key].setdefault(row.properties, [])
            if row.value is not None and row.value not in values:
                values.append(row.value)
        columns = sorted({name for values in properties.values() for name in values})
        def rows():
            for url in urls.iterator():
                info = []
                for field in url_fields:
                    value = getattr(url, field)
                    if field == 'source': value = SOURCE_LABELS.get(value, value)
                    if field == 'status': value = {'active': 'Активен', 'inactive': 'Неактивен'}.get(value, value)
                    info.append(value)
                for price in prices.get(url.pk) or [None]:
                    yield [url.pk in classified, url.pk in (matched_base if source == 'base' else matched_competitors),
                           *info, *[getattr(price, field.name) if price else None for field in price_fields],
                           *['; '.join(properties[url.pk].get(name, [])) for name in columns]]
        sheet(SOURCE_LABELS[source].upper(), ['Товар классифицирован', 'Товар с найденным аналогом',
            *[url_labels[field] for field in url_fields],
            *[price_labels.get(field.name, str(field.verbose_name)) for field in price_fields],
            *columns], rows())


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
                from datetime import datetime
                from django.utils import timezone
                if isinstance(value, datetime) and timezone.is_aware(value):
                    value = timezone.localtime(value).replace(tzinfo=None)
                # Force imported strings to text, including formula-like names/codes.
                cell = WriteOnlyCell(ws, value=value)
                if isinstance(value, str):
                    cell.data_type = 's'
                cells.append(cell)
            ws.append(cells)

    if kind == 'parser_products':
        parser_sheets(sheet)
    else:
        sources = {key: SOURCE_LABELS.get(source, source) for key, source in models.ParserProductUrl.objects.values_list('pk', 'source')}
        own_codes = dict(models.ParserProductUrl.objects.filter(source='base').exclude(own_code__isnull=True).exclude(own_code='').values_list('pk', 'own_code'))
        report = health_report(page_size=None)
        sheet('Проверка данных', ['Раздел', 'Уровень', 'Код проверки', 'Наименование', 'Регион', 'Замечание', 'Исправление', 'Код 1С'],
              ([item[key] for key in ('section', 'severity', 'code', 'nom', 'region', 'message', 'fix', 'code_1c')] for item in report['results']))
        sheet('Срезы', ['Источник', 'Дата'], [('Прайс', report['price_date']), ('Расчёт', (report['snapshot'] or {}).get('date'))])
        from .iprice_models import IPriceRegionalInput, IPriceSourceImport
        from openpyxl import load_workbook
        sheet('Действующая классификация',
              ['Ключ товара', 'Тип', 'Категория', 'Подкатегория', 'Материал', 'Цвет', 'Модификация', 'Группа аналогов', 'Тип товара', 'Ссылка', 'Код 1С', 'Источник'],
              ([r.product_key, r.category, r.subcategory, r.subcategory_type, r.material, r.color, r.modification,
                r.article_number_analogs, r.get_item_type_display(), r.url, own_codes.get(r.product_key), sources.get(r.product_key, 'Источник не найден')]
               for r in models.ParserProductClassification.objects.filter(status='active').order_by('product_key').iterator()))
        sheet('Действующие аналоги', ['Ключ нашего товара', 'Ключ конкурента', 'Способ добавления', 'Код 1С', 'Источник'],
              ([r.product_key_base, r.product_key_competitor, r.get_match_type_display(), own_codes.get(r.product_key_base), sources.get(r.product_key_competitor, 'Источник не найден')]
               for r in models.ParserProductMatch.objects.filter(status='active').order_by('product_key_base', 'product_key_competitor').iterator()))
        sheet('Решения по учёту аналогов', ['Ключ нашего товара', 'Ключ конкурента', 'Участие в расчёте', 'Причина', 'Код 1С', 'Источник'],
              ([r.product_key_base, r.product_key_competitor, r.get_selection_mode_display(), r.reason, own_codes.get(r.product_key_base), sources.get(r.product_key_competitor, 'Источник не найден')]
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
