"""Isolated iPrice tables, based on the Iplast storage contract.

Explicit static declarations: never retarget live models or search_path.
Business services are shared; changes to these contracts require parity tests.
"""
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q


class ParserPrefix(models.Model):
    source = models.CharField(max_length=50, db_index=True, verbose_name='Источник')
    prefix = models.CharField(max_length=255, verbose_name='Префикс')
    shipp_region = models.CharField(max_length=255, db_index=True, verbose_name='Регион', null=True, blank=True)
    date_add = models.DateTimeField(auto_now_add=True, verbose_name='Дата добавления')

    class Meta:
        db_table = '"select_market"."parser_prefix"'
        verbose_name = 'Parser: prefix'
        verbose_name_plural = 'Parser: prefixes'
        constraints = [models.UniqueConstraint(fields=['source', 'prefix'], name='sm_parser_prefix_sour_f2c1df')]

    def __str__(self):
        return f'{self.source}: {self.prefix} -> {self.shipp_region}'

class ParserProductUrl(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_CHOICES = ((STATUS_ACTIVE, 'Active'), (STATUS_INACTIVE, 'Inactive'))
    source = models.CharField(max_length=50, db_index=True, verbose_name='Источник')
    prefix = models.CharField(max_length=255, blank=True, null=True, verbose_name='Префикс')
    url = models.URLField(max_length=1000, verbose_name='URL с префиксом')
    additional_property = models.CharField(max_length=255, blank=True, null=True, verbose_name='Дополнительное свойство')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True, verbose_name='Статус')
    lastmod = models.DateTimeField(blank=True, null=True, verbose_name='Lastmod из sitemap')
    is_loaded = models.BooleanField(default=False, db_index=True, verbose_name='Загружено')
    last_error = models.TextField(blank=True, null=True, verbose_name='Последняя ошибка')
    date_add = models.DateTimeField(auto_now_add=True, verbose_name='Дата добавления')
    date_update = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name='Дата обновления')

    class Meta:
        db_table = '"select_market"."parser_product_url"'
        verbose_name = 'Parser: Product URL'
        verbose_name_plural = 'Parser: Product URLs'
        indexes = [models.Index(fields=['source', 'status'], name='sm_ip_a73e53d8f486'), models.Index(fields=['source', 'is_loaded'], name='sm_ip_945373698cf6'), models.Index(fields=['source', 'date_update'], name='sm_ip_76d9c5b1c16b'), models.Index(fields=['url'], name='sm_ip_91d2c9c648e8')]
        constraints = [models.UniqueConstraint(fields=['source', 'url', 'additional_property'], nulls_distinct=False, name='sm_parser_product_url_e394bf')]

    def __str__(self):
        return f'{self.source}: {self.url}'

class ParserProductProperty(models.Model):
    source = models.CharField(max_length=50, db_index=True, verbose_name='Источник')
    product_key = models.BigIntegerField(db_index=True, verbose_name='Product key')
    url = models.URLField(max_length=1000, blank=True, null=True, verbose_name='URL')
    properties = models.CharField(max_length=500, blank=True, null=True, verbose_name='Свойство')
    value = models.TextField(blank=True, null=True, verbose_name='Значение')
    date_add = models.DateTimeField(auto_now_add=True, verbose_name='Дата добавления')

    class Meta:
        db_table = '"select_market"."parser_product_property"'
        verbose_name = 'Parser: product property'
        verbose_name_plural = 'Parser: product properties'
        indexes = [models.Index(fields=['source', 'product_key'], name='sm_ip_2cd26bde29d5'), models.Index(fields=['product_key'], name='sm_ip_d09fd982f94e')]

    def __str__(self):
        return f'{self.source}: {self.product_key} / {self.properties}'

class TaraProductPrice(models.Model):
    product_key = models.BigIntegerField(db_index=True, verbose_name='Product key')
    url = models.URLField(max_length=1000, blank=True, null=True, verbose_name='URL')
    properties_price = models.CharField(max_length=255, blank=True, null=True, verbose_name='Интервал цены')
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена')
    value_added_tax = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='НДС')
    final_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена без НДС')
    color = models.CharField(max_length=255, blank=True, null=True, verbose_name='Цвет')
    image = models.URLField(max_length=1000, blank=True, null=True, verbose_name='Изображение')
    special_quantity = models.IntegerField(blank=True, null=True, verbose_name='Спец. количество')
    category = models.CharField(max_length=500, blank=True, null=True, verbose_name='Категория')
    name = models.CharField(max_length=1000, blank=True, null=True, verbose_name='Наименование')
    date_add = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата добавления')

    class Meta:
        db_table = '"select_market"."tara_product_price"'
        verbose_name = 'Parser: Tara price'
        verbose_name_plural = 'Parser: Tara prices'
        indexes = [models.Index(fields=['product_key'], name='sm_ip_57a8d29e8cfa'), models.Index(fields=['product_key', 'date_add'], name='sm_ip_cbedfceb5122')]

    def __str__(self):
        return f'{self.product_key}: {self.name}'

class PsProductPrice(models.Model):
    product_key = models.BigIntegerField(db_index=True, verbose_name='Product key')
    url = models.URLField(max_length=1000, blank=True, null=True, verbose_name='URL')
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена')
    value_added_tax = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='НДС')
    final_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена без НДС')
    discount = models.IntegerField(blank=True, null=True, verbose_name='Скидка в карточке товара')
    color = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name='Цвет')
    image = models.TextField(blank=True, null=True, verbose_name='Изображение')
    name = models.CharField(max_length=1000, blank=True, null=True, verbose_name='Наименование товара')
    properties_price = models.CharField(max_length=255, blank=True, null=True, verbose_name='Свойства цены')
    special_quantity = models.IntegerField(blank=True, null=True, verbose_name='Персональные условия')
    date_add = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата добавления')

    class Meta:
        db_table = '"select_market"."ps_product_price"'
        verbose_name = 'Parser: PS price'
        verbose_name_plural = 'Parser: PS prices'
        indexes = [models.Index(fields=['product_key'], name='sm_ip_2ade92882511'), models.Index(fields=['product_key', 'date_add'], name='sm_ip_3ec89744161c')]

    def __str__(self):
        return f'{self.product_key}: {self.name}'

class TtProductPrice(models.Model):
    product_key = models.BigIntegerField(db_index=True, verbose_name='Product key')
    url = models.URLField(max_length=1000, blank=True, null=True, verbose_name='URL')
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена')
    value_added_tax = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='НДС')
    final_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена без НДС')
    additional_property = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name='Дополнительное свойство')
    image = models.TextField(blank=True, null=True, verbose_name='Изображение')
    name = models.CharField(max_length=1000, blank=True, null=True, verbose_name='Наименование товара')
    date_add = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата добавления')

    class Meta:
        db_table = '"select_market"."tt_product_price"'
        verbose_name = 'Parser: TT price'
        verbose_name_plural = 'Parser: TT prices'
        indexes = [models.Index(fields=['product_key'], name='sm_ip_29de1325d13d'), models.Index(fields=['product_key', 'date_add'], name='sm_ip_abea03a6d2f6')]

    def __str__(self):
        return f'{self.product_key}: {self.name}'

class ParserProductMatch(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_CHOICES = ((STATUS_ACTIVE, 'Активен'), (STATUS_INACTIVE, 'Неактивен'))
    MATCH_TYPE_MANUAL = 'manual'
    MATCH_TYPE_AUTO = 'auto'
    MATCH_TYPE_CHOICES = ((MATCH_TYPE_MANUAL, 'Добавлен вручную'), (MATCH_TYPE_AUTO, 'Добавлен автоматически'))
    product_key_base = models.BigIntegerField(db_index=True, verbose_name='Product key нашего товара')
    product_key_competitor = models.BigIntegerField(db_index=True, verbose_name='Product key конкурента')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True, verbose_name='Статус')
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, default=MATCH_TYPE_MANUAL, db_index=True, verbose_name='Способ добавления')
    date_add = models.DateTimeField(auto_now_add=True, verbose_name='Дата добавления')

    class Meta:
        db_table = '"select_market"."parser_product_match"'
        verbose_name = 'Parser: product matching'
        verbose_name_plural = 'Parser: product matches'
        constraints = [models.UniqueConstraint(fields=['product_key_base', 'product_key_competitor'], name='sm_parser_product_mat_4ae8a5')]
        indexes = [models.Index(fields=['product_key_base', 'status'], name='sm_parser_match_base__2243b0'), models.Index(fields=['product_key_competitor', 'status'], name='sm_parser_match_comp__607092'), models.Index(fields=['match_type', 'status'], name='sm_parser_match_type__0b52a6')]

    def __str__(self):
        return f'{self.product_key_base} → {self.product_key_competitor} [{self.match_type}; {self.status}]'

class IPriceCompetitorSelectionOverride(models.Model):
    MODE_AUTO = 'auto'
    MODE_INCLUDE = 'include'
    MODE_EXCLUDE = 'exclude'
    MODE_CHOICES = ((MODE_AUTO, 'Автоматический выбор'), (MODE_INCLUDE, 'Включён вручную'), (MODE_EXCLUDE, 'Исключён вручную'))
    product_key_base = models.BigIntegerField(db_index=True, verbose_name='Product key нашего товара')
    product_key_competitor = models.BigIntegerField(db_index=True, verbose_name='Product key конкурента')
    selection_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_AUTO, db_index=True, verbose_name='Режим участия в расчёте')
    reason = models.TextField(blank=True, default='', verbose_name='Причина ручного решения')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='sm_iprice_competitor_selection_overrides', verbose_name='Кем изменено')
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"select_market"."iprice_competitor_selection_override"'
        verbose_name = 'iPrice: ручной выбор конкурента'
        verbose_name_plural = 'iPrice: ручной выбор конкурентов'
        constraints = [models.UniqueConstraint(fields=['product_key_base', 'product_key_competitor'], name='sm_iprice_competitor__07152d')]
        indexes = [models.Index(fields=['product_key_base', 'selection_mode'], name='sm_iprice_comp_sel_ba_195cc5')]

    def __str__(self):
        return f'{self.product_key_base} -> {self.product_key_competitor}: {self.selection_mode}'

class IPriceCompetitorSelectionChange(models.Model):
    override = models.ForeignKey(IPriceCompetitorSelectionOverride, on_delete=models.PROTECT, related_name='changes', verbose_name='Настройка конкурента')
    snapshot = models.ForeignKey('IPriceSnapshot', null=True, blank=True, on_delete=models.SET_NULL, related_name='competitor_selection_changes', verbose_name='Снапшот')
    previous_mode = models.CharField(max_length=20, blank=True, default='')
    selection_mode = models.CharField(max_length=20, choices=IPriceCompetitorSelectionOverride.MODE_CHOICES)
    reason = models.TextField(blank=True, default='')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='sm_iprice_competitor_selection_changes')
    date_add = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = '"select_market"."iprice_competitor_selection_change"'
        ordering = ('-date_add', '-id')
        indexes = [models.Index(fields=['snapshot', 'date_add'], name='sm_iprice_comp_change_40cf05')]

class BaseProductPrice(models.Model):
    product_key = models.BigIntegerField(db_index=True, verbose_name='Product key')
    url = models.URLField(max_length=1000, blank=True, null=True, verbose_name='URL')
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена')
    value_added_tax = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='НДС')
    final_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена без НДС')
    color = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name='Цвет')
    image = models.TextField(blank=True, null=True, verbose_name='Изображение')
    name = models.CharField(max_length=1000, blank=True, null=True, verbose_name='Наименование товара')
    code_1c = models.CharField(blank=True, null=True, db_index=True, verbose_name='ID товара в 1С', max_length=160)
    date_add = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата добавления')

    class Meta:
        db_table = '"select_market"."base_product_price"'
        verbose_name = 'Parser: Base price'
        verbose_name_plural = 'Parser: Base prices'
        indexes = [models.Index(fields=['product_key'], name='sm_ip_b795c1f65a48'), models.Index(fields=['product_key', 'date_add'], name='sm_ip_c5c903f1a15e'), models.Index(fields=['code_1c'], name='sm_ip_ce39ebe06ca5')]

    def __str__(self):
        return f'{self.product_key}: {self.name}'

class ParserProductClassification(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_CHOICES = ((STATUS_ACTIVE, 'Активен'), (STATUS_INACTIVE, 'Неактивен'))
    ITEM_TYPE_PRODUCT = 'product'
    ITEM_TYPE_COMPONENT = 'component'
    ITEM_TYPE_CHOICES = ((ITEM_TYPE_PRODUCT, 'Товар'), (ITEM_TYPE_COMPONENT, 'Комплектующее'))
    product_key = models.BigIntegerField(unique=True, db_index=True, verbose_name='Product key')
    category = models.CharField(max_length=255, blank=True, null=True, verbose_name='Категория')
    subcategory = models.CharField(max_length=255, blank=True, null=True, verbose_name='Подкатегория')
    subcategory_type = models.CharField(max_length=255, blank=True, null=True, verbose_name='Тип подкатегории')
    material = models.CharField(max_length=255, blank=True, null=True, verbose_name='Материал')
    color = models.CharField(max_length=255, blank=True, null=True, verbose_name='Цвет')
    modification = models.CharField(max_length=255, blank=True, null=True, verbose_name='Модификация')
    article_number_analogs = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name='Артикул группы аналогов')
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES, blank=True, null=True, db_index=True, verbose_name='Тип товара')
    url = models.TextField(blank=True, null=True, verbose_name='URL')
    image = models.TextField(blank=True, null=True, verbose_name='Изображение')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True, verbose_name='Статус')
    date_add = models.DateTimeField(auto_now_add=True, verbose_name='Дата добавления')
    date_update = models.DateTimeField(blank=True, null=True, verbose_name='Дата изменения')

    class Meta:
        db_table = '"select_market"."parser_product_classification"'
        verbose_name = 'Parser: product classification'
        verbose_name_plural = 'Parser: products classification'

    def __str__(self):
        return f'{self.product_key} [{self.status}]'





class ParserMasterPipelineRun(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_WAITING_TARA = 'waiting_tara'
    STATUS_WAITING_SESSION = 'waiting_session'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [(STATUS_QUEUED, 'Queued'), (STATUS_RUNNING, 'Running'), (STATUS_SUCCESS, 'Success'), (STATUS_FAILED, 'Failed'), (STATUS_WAITING_TARA, 'Waiting for Tara'), (STATUS_WAITING_SESSION, 'Waiting for session'), (STATUS_CANCELLED, 'Cancelled')]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True)
    current_step = models.CharField(max_length=100, blank=True, default='')
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='sm_parser_master_pipeline_runs')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default='')
    result = models.JSONField(default=dict, blank=True)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."parser_master_pipeline_run"'
        ordering = ['-date_add']

    def __str__(self):
        return f'Parser pipeline #{self.pk}: {self.status}'

class IPriceSnapshot(models.Model):
    STATUS_BUILDING = 'building'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = ((STATUS_BUILDING, 'Выполняется'), (STATUS_SUCCESS, 'Рассчитан'), (STATUS_FAILED, 'Ошибка'))
    calculation_date = models.DateField(db_index=True, verbose_name='Дата расчета')
    version_number = models.PositiveIntegerField(unique=True, db_index=True, verbose_name='Глобальный номер версии')
    revision_for_date = models.PositiveIntegerField(verbose_name='Номер версии за дату')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_BUILDING, db_index=True, verbose_name='Статус')
    is_current = models.BooleanField(default=False, db_index=True, verbose_name='Текущая версия за дату')
    is_active = models.BooleanField(default=False, db_index=True, verbose_name='Активный окончательный расчет')
    was_active = models.BooleanField(default=False, db_index=True, verbose_name='Была активной')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='sm_created_iprice_snapshots', verbose_name='Кем создан')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата завершения')
    activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='sm_activated_iprice_snapshots', verbose_name='Кем активирован')
    activated_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата активации')
    error = models.TextField(blank=True, default='', verbose_name='Ошибка')
    parameters = models.JSONField(default=dict, blank=True, verbose_name='Параметры запуска')
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."iprice_snapshot"'
        verbose_name = 'iPrice snapshot'
        verbose_name_plural = 'iPrice snapshots'
        constraints = [models.UniqueConstraint(fields=['calculation_date', 'revision_for_date'], name='sm_iprice_snapshot_da_c2dc58'), models.UniqueConstraint(fields=['calculation_date'], condition=Q(is_current=True), name='sm_iprice_snapshot_cu_631a06'), models.UniqueConstraint(fields=['is_active'], condition=Q(is_active=True), name='sm_iprice_snapshot_on_0c5dd6')]
        indexes = [models.Index(fields=['calculation_date', 'is_current'], name='sm_iprice_snap_date_c_aeba5a'), models.Index(fields=['status', 'created_at'], name='sm_iprice_snap_status_7b618f')]
        ordering = ['-created_at', '-id']

    @property
    def display_version(self):
        return f'v{self.version_number}-{self.calculation_date:%d.%m.%y}'

    def __str__(self):
        return self.display_version

class IPriceSnapshotProduct(models.Model):
    PRICING_METHOD_ANALOG = 'analog'
    PRICING_METHOD_EXCLUSIVE = 'exclusive'
    PRICING_METHOD_CHOICES = ((PRICING_METHOD_ANALOG, 'Аналог'), (PRICING_METHOD_EXCLUSIVE, 'Эксклюзив'))
    STATUS_SUCCESS = 'success'
    STATUS_WARNING = 'warning'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = ((STATUS_SUCCESS, 'Рассчитано'), (STATUS_WARNING, 'Есть предупреждения'), (STATUS_ERROR, 'Расчет невозможен'))
    snapshot = models.ForeignKey(IPriceSnapshot, on_delete=models.CASCADE, related_name='products', verbose_name='Snapshot')
    base_product_key = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name='Product key нашего товара')
    group_1 = models.CharField(max_length=255, blank=True, default='')
    group_2 = models.CharField(max_length=255, blank=True, default='')
    group_3 = models.CharField(max_length=255, blank=True, default='')
    group_4 = models.CharField(max_length=255, blank=True, default='')
    is_classified = models.BooleanField(default=False)
    code_1c = models.CharField(db_index=True, verbose_name='Код номенклатуры 1С', max_length=160)
    nom = models.CharField(max_length=1000, null=True, blank=True, verbose_name='Наименование')
    nom_hier_code = models.CharField(max_length=255, null=True, blank=True, verbose_name='Код иерархии')
    nom_hier = models.CharField(max_length=1000, null=True, blank=True, verbose_name='Иерархия')
    nom_view = models.CharField(max_length=255, null=True, blank=True, verbose_name='Вид номенклатуры')
    nom_category = models.CharField(max_length=255, null=True, blank=True, verbose_name='Категория номенклатуры')
    nom_group = models.CharField(max_length=255, null=True, blank=True, verbose_name='Группа номенклатуры')
    assortment_matrix_status = models.TextField(null=True, blank=True, verbose_name='САМ')
    our_offer = models.TextField(null=True, blank=True, verbose_name='Наши предложения')
    category = models.CharField(max_length=255, null=True, blank=True, verbose_name='Внутренняя категория')
    subcategory = models.CharField(max_length=255, null=True, blank=True, verbose_name='Внутренняя подкатегория')
    subcategory_type = models.CharField(max_length=255, null=True, blank=True, verbose_name='Тип подкатегории')
    color = models.CharField(max_length=255, null=True, blank=True, verbose_name='Цвет')
    material = models.CharField(max_length=255, null=True, blank=True, verbose_name='Материал')
    modification = models.CharField(max_length=255, null=True, blank=True, verbose_name='Модификация')
    image = models.TextField(null=True, blank=True, verbose_name='Изображение')
    url = models.TextField(null=True, blank=True, verbose_name='URL')
    item_type = models.CharField(max_length=20, db_index=True, verbose_name='Тип позиции')
    pricing_method = models.CharField(max_length=20, choices=PRICING_METHOD_CHOICES, db_index=True, verbose_name='Метод ценообразования')
    competitor_count = models.PositiveIntegerField(default=0, verbose_name='Количество конкурентов')
    competitor_rrp_min = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Минимальная РРЦ конкурентов')
    competitor_rrp_max = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Максимальная РРЦ конкурентов')
    competitor_rrp_median = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Медианная РРЦ конкурентов')
    current_retail_min = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Минимальная текущая розница')
    current_retail_max = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Максимальная текущая розница')
    current_retail_median = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Медианная текущая розница')
    current_vs_competitor_amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Отклонение от медианы, руб.')
    current_vs_competitor_percent = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, verbose_name='Отклонение от медианы, доля')
    effective_approved_rrp_median = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Медиана итоговой РРЦ')
    current_vs_approved_amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Разница розницы и итоговой РРЦ')
    calculation_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS, db_index=True, verbose_name='Статус расчета')
    warning_codes = models.JSONField(default=list, blank=True, verbose_name='Предупреждения')
    error_codes = models.JSONField(default=list, blank=True, verbose_name='Ошибки')
    calculation_details = models.JSONField(default=dict, blank=True, verbose_name='Детали расчета')
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."iprice_snapshot_product"'
        verbose_name = 'iPrice snapshot product'
        verbose_name_plural = 'iPrice snapshot products'
        constraints = [models.UniqueConstraint(fields=['snapshot', 'base_product_key'], name='sm_iprice_snap_produc_fbbf13')]
        indexes = [models.Index(fields=['snapshot', 'code_1c'], name='sm_iprice_sp_snap_cod_863fc0'), models.Index(fields=['snapshot', 'pricing_method'], name='sm_iprice_sp_snap_met_652c91'), models.Index(fields=['snapshot', 'calculation_status'], name='sm_iprice_sp_snap_sta_928f91')]

    def __str__(self):
        return f'{self.snapshot.display_version} | {self.code_1c} | {self.nom}'

class IPriceSnapshotCompetitor(models.Model):
    snapshot_product = models.ForeignKey(IPriceSnapshotProduct, on_delete=models.CASCADE, related_name='competitors', verbose_name='Товар snapshot')
    competitor_product_key = models.BigIntegerField(db_index=True, verbose_name='Product key конкурента')
    source = models.CharField(max_length=50, db_index=True, verbose_name='Источник')
    url = models.TextField(null=True, blank=True, verbose_name='URL конкурента')
    prefix = models.CharField(max_length=255, null=True, blank=True, verbose_name='Префикс')
    competitor_price_date = models.DateField(null=True, blank=True, db_index=True, verbose_name='Дата конкурентной цены')
    competitor_final_price_max = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Максимальная цена без НДС')
    source_price_row_id = models.BigIntegerField(null=True, blank=True, verbose_name='ID выбранной строки цены')
    price_variants = models.JSONField(default=list, blank=True, verbose_name='Все варианты цены за день')
    is_all_regions = models.BooleanField(default=False, db_index=True, verbose_name='Применяется ко всем регионам')
    applicable_regions = models.JSONField(default=list, blank=True, verbose_name='Применимые регионы продажи')
    base_analog = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, verbose_name='Коэффициент аналога')
    preliminary_rrp = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Предварительная РРЦ')
    calculation_status = models.CharField(max_length=20, default='success', db_index=True, verbose_name='Статус расчета')
    warning_codes = models.JSONField(default=list, blank=True, verbose_name='Предупреждения')
    error_codes = models.JSONField(default=list, blank=True, verbose_name='Ошибки')
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."iprice_snapshot_competitor"'
        verbose_name = 'iPrice snapshot competitor'
        verbose_name_plural = 'iPrice snapshot competitors'
        constraints = [models.UniqueConstraint(fields=['snapshot_product', 'competitor_product_key'], name='sm_iprice_snap_produc_41e3ae')]
        indexes = [models.Index(fields=['snapshot_product', 'source'], name='sm_iprice_sc_product__9e6223'), models.Index(fields=['source', 'competitor_product_key', 'competitor_price_date'], name='sm_iprice_sc_source_k_8d343d')]

    def __str__(self):
        return f'{self.snapshot_product.base_product_key} -> {self.source}:{self.competitor_product_key}'

class IPriceSnapshotRegion(models.Model):
    historical_variant = models.CharField(max_length=64, default='', blank=True, editable=False)
    STATUS_SUCCESS = 'success'
    STATUS_WARNING = 'warning'
    STATUS_ERROR = 'error'
    snapshot_product = models.ForeignKey(IPriceSnapshotProduct, on_delete=models.CASCADE, related_name='regions', verbose_name='Товар snapshot')
    sale_region = models.CharField(max_length=255, db_index=True, verbose_name='Регион продажи')
    product_cost_source_id = models.BigIntegerField(null=True, blank=True, verbose_name='ID исходной себестоимости')
    nomenclature_price_source_id = models.BigIntegerField(null=True, blank=True, verbose_name='ID исходной цены 1С')
    product_cost_month = models.DateField(null=True, blank=True, verbose_name='Месяц себестоимости')
    nomenclature_price_date = models.DateField(null=True, blank=True, verbose_name='Дата цены 1С')
    current_retail = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Текущая розница')
    current_small = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Текущий малый опт')
    current_medium = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Текущий средний опт')
    current_large = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Текущий крупный опт')
    product_cost = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Себестоимость')
    quantity_eurotruck = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Количество в еврофуре')
    logistics_unit = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, verbose_name='Логистика на единицу')
    cost_with_logistics = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, verbose_name='Себестоимость с логистикой')
    regional_competitor_count = models.PositiveIntegerField(default=0, verbose_name='Количество конкурентов региона')
    regional_competitor_rrp_min = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Минимальная РРЦ конкурентов региона')
    regional_competitor_rrp_max = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Максимальная РРЦ конкурентов региона')
    regional_competitor_rrp_median = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Медианная РРЦ конкурентов региона')
    base_analog = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, verbose_name='Коэффициент аналога')
    base_exclusive = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, verbose_name='Коэффициент эксклюзива')
    minimum_margin = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, verbose_name='Минимальная маржинальность')
    discount_small = models.DecimalField(max_digits=7, decimal_places=6, null=True, blank=True, verbose_name='Скидка small')
    discount_medium = models.DecimalField(max_digits=7, decimal_places=6, null=True, blank=True, verbose_name='Скидка medium')
    discount_large = models.DecimalField(max_digits=7, decimal_places=6, null=True, blank=True, verbose_name='Скидка large')
    preliminary_rrp = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Предварительная РРЦ')
    minimum_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Минимальная цена')
    calculated_rrp = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Расчетная РРЦ')
    default_approved_rrp = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='РРЦ по умолчанию')
    calculated_small = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Расчетный малый опт')
    calculated_medium = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Расчетный средний опт')
    calculated_large = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Расчетный крупный опт')
    margin_current = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, verbose_name='Текущая маржа')
    margin_calculated = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, verbose_name='Расчетная маржа')
    current_vs_calculated_percent = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, verbose_name='Отклонение текущей цены')
    calculation_status = models.CharField(max_length=20, default=STATUS_SUCCESS, db_index=True, verbose_name='Статус расчета')
    warning_codes = models.JSONField(default=list, blank=True, verbose_name='Предупреждения')
    error_codes = models.JSONField(default=list, blank=True, verbose_name='Ошибки')
    calculation_details = models.JSONField(default=dict, blank=True, verbose_name='Детали расчета')
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."iprice_snapshot_region"'
        verbose_name = 'iPrice snapshot region'
        verbose_name_plural = 'iPrice snapshot regions'
        constraints = [models.UniqueConstraint(fields=['snapshot_product', 'sale_region', 'historical_variant'], name='sm_iprice_region_variant_key')]
        indexes = [models.Index(fields=['snapshot_product', 'sale_region'], name='sm_iprice_sr_product__2bc50b'), models.Index(fields=['calculation_status'], name='sm_iprice_sr_status_i_e27fa9')]

    def __str__(self):
        return f'{self.snapshot_product.code_1c} | {self.sale_region}'

class IPriceSnapshotApproval(models.Model):
    snapshot_region = models.ForeignKey(IPriceSnapshotRegion, on_delete=models.CASCADE, related_name='approvals', verbose_name='Региональная строка')
    revision = models.PositiveIntegerField(verbose_name='Версия утверждения')
    approved_rrp = models.DecimalField(max_digits=18, decimal_places=4, verbose_name='Утвержденная РРЦ')
    approved_small = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Утвержденный малый опт')
    approved_medium = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Утвержденный средний опт')
    approved_large = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, verbose_name='Утвержденный крупный опт')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='sm_iprice_approvals', verbose_name='Кем утверждено')
    approved_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата утверждения')
    comment = models.TextField(blank=True, default='', verbose_name='Комментарий')
    is_current = models.BooleanField(default=True, db_index=True, verbose_name='Текущее утверждение')
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"select_market"."iprice_snapshot_approval"'
        verbose_name = 'iPrice snapshot approval'
        verbose_name_plural = 'iPrice snapshot approvals'
        constraints = [models.UniqueConstraint(fields=['snapshot_region', 'revision'], name='sm_iprice_approval_re_bbb370'), models.UniqueConstraint(fields=['snapshot_region'], condition=Q(is_current=True), name='sm_iprice_approval_cu_3920e9')]
        indexes = [models.Index(fields=['snapshot_region', 'is_current'], name='sm_iprice_approval_cu_84841d')]

    def __str__(self):
        return f'{self.snapshot_region} | revision={self.revision} | rrp={self.approved_rrp}'

class IPriceParameterChangeLog(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_ERROR = 'error'
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='sm_iprice_parameter_change_logs')
    snapshot_id = models.BigIntegerField(db_index=True)
    mode = models.CharField(max_length=20)
    filters = models.JSONField(default=dict, blank=True)
    search = models.TextField(blank=True, default='')
    changes = models.JSONField(default=dict)
    affected = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default=STATUS_PENDING, db_index=True)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = '"select_market"."iprice_parameter_change_log"'
        ordering = ('-created_at', '-id')
        verbose_name = 'Changing iPrice settings'
        verbose_name_plural = 'Changing iPrice settings'

    def __str__(self):
        return f'iPrice snapshot {self.snapshot_id}: {self.status}'

class IPricePriceZoneConfig(models.Model):
    below_market_threshold = models.DecimalField(max_digits=8, decimal_places=6, default=Decimal('-0.03'), verbose_name='Нижний порог рынка')
    above_market_threshold = models.DecimalField(max_digits=8, decimal_places=6, default=Decimal('0.03'), verbose_name='Верхний порог рынка')
    critical_threshold = models.DecimalField(max_digits=8, decimal_places=6, default=Decimal('0.10'), verbose_name='Критический порог')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Активная конфигурация')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='sm_created_iprice_price_zone_configs', verbose_name='Кем создана')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')

    class Meta:
        db_table = '"select_market"."iprice_price_zone_config"'
        ordering = ('-created_at', '-id')
        verbose_name = 'iPrice price zone configuration'
        verbose_name_plural = 'iPrice price zone configurations'
        constraints = (models.UniqueConstraint(fields=('is_active',), condition=models.Q(is_active=True), name='sm_iprice_one_active__791898'), models.CheckConstraint(condition=models.Q(below_market_threshold__lt=0) & models.Q(above_market_threshold__gt=0) & models.Q(critical_threshold__gt=0) & models.Q(below_market_threshold__lt=models.F('above_market_threshold')) & models.Q(above_market_threshold__lt=models.F('critical_threshold')), name='sm_iprice_price_zone__8f69aa'))

    def __str__(self):
        return f'{self.below_market_threshold} / {self.above_market_threshold} / {self.critical_threshold}'
