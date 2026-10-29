"""Мастер-данные (E-01 – E-07)."""
from .iprice_models import IPricePriceImport, IPriceSourceImport, NomenclaturePrice, IPriceRegionalInput, IPriceLegacyArchive  # noqa: F401
from django.conf import settings
from django.db import models
from django.utils import timezone


class Channel(models.Model):
    CODES = [("ECOM", "Интернет-магазин"), ("B2B", "B2B-портал"), ("MP", "Маркетплейсы"), ("RETAIL", "Сетевая торговля")]
    code = models.CharField(max_length=10, unique=True, choices=CODES)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = '"select_market"."channel"'
        ordering = ["id"]
        verbose_name = "канал"
        verbose_name_plural = "каналы"

    def __str__(self):
        return self.name


class Node(models.Model):
    """Узел продуктовой иерархии: уровень 1 – категория, 2 – товарная группа."""
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    level = models.PositiveSmallIntegerField()
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=255)

    class Meta:
        db_table = '"select_market"."node"'
        ordering = ["level", "name"]
        verbose_name = "узел иерархии"
        verbose_name_plural = "узлы иерархии"

    def __str__(self):
        return self.name

    def ancestor_ids(self):
        ids, n = [], self.parent
        while n is not None:
            ids.append(n.id)
            n = n.parent
        return ids


class Product(models.Model):
    STATUS = [("NEW", "Новинка"), ("ACTIVE", "В продаже"), ("PHASING_OUT", "Выводится"), ("DISCONTINUED", "Выведен")]
    sku = models.CharField("Код SKU", max_length=40, unique=True)
    name = models.CharField("Наименование", max_length=255)
    gtin = models.CharField("GTIN", max_length=14, blank=True)
    node = models.ForeignKey(Node, on_delete=models.PROTECT, verbose_name="Товарная группа")
    uom = models.CharField("Единица", max_length=10, default="шт")
    pack_multiple = models.DecimalField("Кратность", max_digits=12, decimal_places=3, default=1)
    lifecycle_status = models.CharField("Статус ЖЦ", max_length=14, choices=STATUS, default="ACTIVE")
    launch_date = models.DateField("Дата ввода", null=True, blank=True)
    phaseout_date = models.DateField("Дата вывода", null=True, blank=True)
    lead_time_days = models.PositiveIntegerField("Срок выполнения заказа, дней", default=42)
    price = models.DecimalField("Регулярная цена", max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = '"select_market"."product"'
        ordering = ["sku"]
        verbose_name = "SKU"
        verbose_name_plural = "SKU"

    def __str__(self):
        return f"{self.sku} {self.name}"


class Customer(models.Model):
    TYPES = [("ECOM_STORE", "Интернет-магазин"), ("B2B_CLIENT", "B2B-клиент"), ("MARKETPLACE", "Площадка"), ("RETAIL_CHAIN", "Сеть")]
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=255)
    customer_type = models.CharField(max_length=14, choices=TYPES)
    channel = models.ForeignKey(Channel, on_delete=models.PROTECT)
    is_key_account = models.BooleanField(default=False)
    cover_days = models.PositiveIntegerField("Целевое покрытие запаса сети, дней (PRM-40)", default=21)
    order_weekday = models.PositiveSmallIntegerField("День заказа сети (0 – пн)", default=0)

    class Meta:
        db_table = '"select_market"."customer"'
        ordering = ["channel_id", "name"]
        verbose_name = "клиент"
        verbose_name_plural = "клиенты"

    def __str__(self):
        return self.name


class Location(models.Model):
    TYPES = [("OWN_WAREHOUSE", "Склад компании"), ("MP_WAREHOUSE", "Склад площадки"), ("CHAIN_DC", "РЦ сети")]
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=255)
    location_type = models.CharField(max_length=14, choices=TYPES)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT)
    region = models.CharField(max_length=40, blank=True)
    review_days = models.PositiveIntegerField("Период между поставками, дней", default=7)
    transit_days = models.PositiveIntegerField("Транзит, дней", default=3)
    acceptance_days = models.PositiveIntegerField("Приёмка, дней", default=2)
    acceptance_limit_week = models.DecimalField("Лимит приёмки в неделю, шт.", max_digits=14, decimal_places=3, null=True, blank=True)

    class Meta:
        db_table = '"select_market"."location"'
        ordering = ["code"]
        verbose_name = "склад"
        verbose_name_plural = "склады"

    def __str__(self):
        return self.name


class Series(models.Model):
    """Ряд – базовый уровень прогноза SKU × клиент × склад (М 6.1.2, CN-01)."""
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="series")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    channel = models.ForeignKey(Channel, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = '"select_market"."series"'
        unique_together = [("product", "customer", "location")]
        ordering = ["product__sku", "customer__code"]
        verbose_name = "ряд"
        verbose_name_plural = "ряды"

    def __str__(self):
        return f"{self.product.sku} / {self.customer.name} / {self.location.code}"


D = dict(max_digits=16, decimal_places=3)
M = dict(max_digits=16, decimal_places=2)
R = dict(max_digits=9, decimal_places=6)

class PriceList(models.Model):
    KIND = [("LIST", "Прайс-лист"), ("BUDGET", "Цены бюджета")]
    code = models.CharField("Код", max_length=40, unique=True)
    name = models.CharField("Наименование", max_length=255)
    kind = models.CharField("Назначение", max_length=6, choices=KIND, default="LIST")
    channel = models.ForeignKey("select_market.Channel", null=True, blank=True, on_delete=models.PROTECT, verbose_name="Канал")
    customer = models.ForeignKey("select_market.Customer", null=True, blank=True, on_delete=models.PROTECT, verbose_name="Клиент")
    currency = models.CharField("Валюта", max_length=3, default="RUB")

    class Meta:
        db_table = '"select_market"."price_list"'
        ordering = ["kind", "code"]
        verbose_name = "прайс-лист"
        verbose_name_plural = "прайс-листы"

    def __str__(self):
        return f"{self.code} {self.name}"


class PriceListItem(models.Model):
    price_list = models.ForeignKey(PriceList, on_delete=models.PROTECT, related_name="items")
    product = models.ForeignKey("select_market.Product", on_delete=models.PROTECT)
    price = models.DecimalField("Цена без НДС", **M)
    valid_from = models.DateField("Действует с")
    valid_to = models.DateField("Действует по", null=True, blank=True)

    class Meta:
        db_table = '"select_market"."price_list_item"'
        unique_together = [("price_list", "product", "valid_from")]
        ordering = ["price_list", "product__sku", "valid_from"]


class PriceChange(models.Model):
    """Строка плана изменения цен (E-73)."""
    LEVEL = [("SKU", "SKU"), ("GROUP", "Товарная группа"), ("CATEGORY", "Категория")]
    STATUS = [("PROJECT", "Проект"), ("APPROVED", "Утверждён"), ("ACTIVE", "Действует"), ("CANCELLED", "Отменён")]
    import_key = models.CharField(max_length=64, unique=True)
    level = models.CharField("Уровень", max_length=8, choices=LEVEL)
    product = models.ForeignKey("select_market.Product", null=True, blank=True, on_delete=models.PROTECT)
    node = models.ForeignKey("select_market.Node", null=True, blank=True, on_delete=models.PROTECT)
    channel = models.ForeignKey("select_market.Channel", null=True, blank=True, on_delete=models.PROTECT)
    customer = models.ForeignKey("select_market.Customer", null=True, blank=True, on_delete=models.PROTECT)
    effective_date = models.DateField("Дата вступления в силу")
    change_pct = models.DecimalField("Изменение, доля", **R, null=True, blank=True)
    new_price = models.DecimalField("Новая цена", **M, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="PROJECT")
    decision_ref = models.CharField("Реквизиты решения", max_length=255, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = '"select_market"."price_change"'
        ordering = ["effective_date", "id"]

    def applies_to(self, product, channel_id, customer_id):
        if self.channel_id and self.channel_id != channel_id:
            return False
        if self.customer_id and self.customer_id != customer_id:
            return False
        if self.level == "SKU":
            return self.product_id == product.id
        if self.level == "GROUP":
            return self.node_id == product.node_id
        return self.node_id == product.node.parent_id

    @property
    def target_label(self):
        return str(self.product) if self.level == "SKU" else (self.node.name if self.node else "—")


class CustomerCondition(models.Model):
    """Условия клиента (E-74)."""
    customer = models.ForeignKey("select_market.Customer", on_delete=models.PROTECT, related_name="conditions")
    discount_pct = models.DecimalField("Договорная скидка", **R, default=0)
    stacking_allowed = models.BooleanField("Скидки акции и от суммы заказа суммируются", default=True)
    marketing_bonus_pct = models.DecimalField("Маркетинговые и логистические бонусы", **R, default=0)
    mp_cofinance_pct = models.DecimalField("Софинансирование акций площадки", **R, default=0)
    valid_from = models.DateField("Действует с")

    class Meta:
        db_table = '"select_market"."customer_condition"'
        unique_together = [("customer", "valid_from")]
        ordering = ["customer", "-valid_from"]


class DiscountScale(models.Model):
    """Шкала скидок от суммы заказа или накопительного бонуса (E-75)."""
    KIND = [("ORDER_TIER", "Скидка от суммы заказа"), ("REBATE", "Накопительный бонус")]
    MODE = [("ALL_UNITS", "На весь объём"), ("PROGRESSIVE", "Прогрессивная")]
    PERIOD = [("ORDER", "Заказ"), ("WEEK", "Неделя"), ("MONTH", "Месяц"), ("QUARTER", "Квартал"), ("YEAR", "Год")]
    BASE = [("AMOUNT", "Сумма в ценах счёта"), ("QTY", "Количество")]
    code = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey("select_market.Customer", null=True, blank=True, on_delete=models.PROTECT)
    channel = models.ForeignKey("select_market.Channel", null=True, blank=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=KIND)
    mode = models.CharField(max_length=11, choices=MODE, default="ALL_UNITS")
    period = models.CharField(max_length=7, choices=PERIOD, default="ORDER")
    base = models.CharField(max_length=6, choices=BASE, default="AMOUNT")
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        db_table = '"select_market"."discount_scale"'
        ordering = ["kind", "code"]

    def steps_list(self):
        return [(float(s.threshold), float(s.rate)) for s in self.steps.order_by("threshold")]


class ScaleStep(models.Model):
    scale = models.ForeignKey(DiscountScale, on_delete=models.PROTECT, related_name="steps")
    threshold = models.DecimalField(**M)
    rate = models.DecimalField(**R)

    class Meta:
        db_table = '"select_market"."scale_step"'
        unique_together = [("scale", "threshold")]
        ordering = ["threshold"]


class OrderHeader(models.Model):
    """Заказ с суммой для профиля сумм заказов (E-79); данных покупателей нет."""
    order_no = models.CharField(max_length=60)
    source = models.CharField(max_length=40, default="ERP")
    customer = models.ForeignKey("select_market.Customer", on_delete=models.PROTECT)
    order_date = models.DateField(db_index=True)
    amount = models.DecimalField(**M)
    qty = models.DecimalField(**D, null=True, blank=True)

    class Meta:
        db_table = '"select_market"."order_header"'
        unique_together = [("source", "order_no")]


# Isolated iPrice storage; explicit imports register models with Django.
from .iprice_domain_models import (  # noqa: E402, F401
    ParserPrefix,
    ParserProductUrl,
    ParserProductProperty,
    TaraProductPrice,
    PsProductPrice,
    TtProductPrice,
    ParserProductMatch,
    IPriceCompetitorSelectionOverride,
    IPriceCompetitorSelectionChange,
    BaseProductPrice,
    ParserProductClassification,
    ClassificationChange,
    ParserMasterPipelineRun,
    IPriceSnapshot,
    IPriceSnapshotProduct,
    IPriceSnapshotCompetitor,
    IPriceSnapshotRegion,
    IPriceSnapshotApproval,
    IPriceParameterChangeLog,
    IPricePriceZoneConfig,
)

from .iprice_tara_models import (  # noqa: E402, F401
    TaraRun,
    TaraItem,
    TaraCoordinator,
    TaraFetch,
    TaraWorker,
)
