from django.db import models
from django.db.models import Q
from django.conf import settings
from .tara_models import TaraCoordinator, TaraItem, TaraRun, TaraFetch, TaraWorker




class Dataset(models.Model):
    name = models.CharField(max_length=255)

    source_file = models.FileField(
        upload_to="datasets/"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name


class DatasetRow(models.Model):
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name="rows"
    )

    data = models.JSONField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.dataset.name} #{self.id}"




class FbProject(models.Model):
    folder_lvl1 = models.CharField(max_length=255, blank=True, null=True)
    folder_lvl2 = models.CharField(max_length=255, blank=True, null=True)
    folder_lvl3 = models.CharField(max_length=255, blank=True, null=True)

    project_name = models.CharField(max_length=255, blank=True, null=True)
    project_manager = models.CharField(max_length=255, blank=True, null=True)

    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)

    project_status = models.CharField(max_length=255, blank=True, null=True)
    project_type = models.CharField(max_length=255, blank=True, null=True)
    department = models.CharField(max_length=255, blank=True, null=True)

    subtask_id = models.CharField(max_length=255, blank=True, null=True)
    subtask_name = models.CharField(max_length=255, blank=True, null=True)
    subtask_responsible = models.CharField(max_length=255, blank=True, null=True)

    subtask_start_date = models.DateField(blank=True, null=True)
    subtask_end_date = models.DateField(blank=True, null=True)

    actual_start_project = models.DateField(blank=True, null=True)
    actual_end_project = models.DateField(blank=True, null=True)
    actual_start_subtask = models.DateField(blank=True, null=True)
    actual_end_subtask = models.DateField(blank=True, null=True)

    subtask_status = models.CharField(max_length=255, blank=True, null=True)

    m_quarter_text = models.CharField(max_length=255, blank=True, null=True)
    deviation = models.CharField(max_length=255, blank=True, null=True)
    deviation_project = models.CharField(max_length=255, blank=True, null=True)

    number = models.IntegerField(blank=True, null=True)

    predecessor = models.CharField(max_length=255, blank=True, null=True)
    code_sdr = models.CharField(max_length=255, blank=True, null=True)
    type_depend = models.CharField(max_length=255, blank=True, null=True)
    delay = models.CharField(max_length=255, blank=True, null=True)
    unit = models.CharField(max_length=255, blank=True, null=True)

    hier_subtask1 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask2 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask3 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask4 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask5 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask6 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask7 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask8 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask9 = models.CharField(max_length=255, blank=True, null=True)
    hier_subtask10 = models.CharField(max_length=255, blank=True, null=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fb_project"

    def __str__(self):
        return self.project_name or f"Проект {self.id}"




class YdWordstatFor(models.Model):
    feature = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    category = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    phrase = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    year = models.IntegerField(blank=True, null=True, db_index=True)

    month_1 = models.BigIntegerField(blank=True, null=True)
    month_2 = models.BigIntegerField(blank=True, null=True)
    month_3 = models.BigIntegerField(blank=True, null=True)
    month_4 = models.BigIntegerField(blank=True, null=True)
    month_5 = models.BigIntegerField(blank=True, null=True)
    month_6 = models.BigIntegerField(blank=True, null=True)
    month_7 = models.BigIntegerField(blank=True, null=True)
    month_8 = models.BigIntegerField(blank=True, null=True)
    month_9 = models.BigIntegerField(blank=True, null=True)
    month_10 = models.BigIntegerField(blank=True, null=True)
    month_11 = models.BigIntegerField(blank=True, null=True)
    month_12 = models.BigIntegerField(blank=True, null=True)

    total = models.BigIntegerField(blank=True, null=True)

    average = models.DecimalField(max_digits=22, decimal_places=2, blank=True, null=True)
    growth = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)

    monthS_1 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_2 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_3 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_4 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_5 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_6 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_7 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_8 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_9 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_10 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_11 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    monthS_12 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)

    desktop = models.BigIntegerField(blank=True, null=True)
    phone = models.BigIntegerField(blank=True, null=True)
    tablet = models.BigIntegerField(blank=True, null=True)
    other_device = models.BigIntegerField(blank=True, null=True)

    ekb_macroregion = models.BigIntegerField(blank=True, null=True)
    kras_macroregion = models.BigIntegerField(blank=True, null=True)
    mos_macroregion = models.BigIntegerField(blank=True, null=True)
    nign_macroregion = models.BigIntegerField(blank=True, null=True)
    novos_macroregion = models.BigIntegerField(blank=True, null=True)
    spb_macroregion = models.BigIntegerField(blank=True, null=True)
    sng_macroregion = models.BigIntegerField(blank=True, null=True)
    other_macroregion = models.BigIntegerField(blank=True, null=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_for"
        verbose_name = "YD Wordstat"
        verbose_name_plural = "YD Wordstats"

    def __str__(self):
        return f"{self.phrase} ({self.year})"



class FBPurchasesUse(models.Model):
    quantity_1C = models.DecimalField(max_digits=15, decimal_places=0, blank=True, null=True)
    revenue_1C = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    VAT_1C = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    nomenclature_code = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    date_draft = models.DateField("Дата", blank=True, null=True, db_index=True)
    party_status = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    partner = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    nomenclature = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fb_purchases_use"
        verbose_name = "Purchase"
        verbose_name_plural = "Purchases"

    def __str__(self):
        return self.nomenclature or f"Purchase {self.id}"


class FBPurchasesUseIndicator(models.Model):
    indicator = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    date_draft = models.DateField("Дата", blank=True, null=True, db_index=True)

    class Meta:
        db_table = "fb_purchases_ind"
        verbose_name = "Purchase target value"
        verbose_name_plural = "Purchase target values"

    def __str__(self):
        return str(self.indicator) if self.indicator is not None else f"Purchase target value {self.id}"
    



class TurnoverClear(models.Model):
    date_stock = models.DateField("Остаток на дату")
    date_start = models.DateField("Период с", db_index=True)
    date_end = models.DateField("Период по", db_index=True)

    warehouse_group = models.CharField("Группа по складу", max_length=255, blank=True, null=True, db_index=True)
    warehouse = models.CharField("Склад", max_length=255, blank=True, null=True, db_index=True)
    nomenclature = models.CharField("Номенклатура", max_length=255, blank=True, null=True, db_index=True)

    quantity = models.CharField("Качество", max_length=255, blank=True, null=True)
    price = models.DecimalField("Цена", max_digits=9, decimal_places=2, blank=True, null=True)
    amount_day = models.IntegerField("Количество дней", blank=True, null=True)

    middle_stock = models.DecimalField("Средний запас", max_digits=10, decimal_places=2, blank=True, null=True, db_index=True)
    middle_rubstock = models.DecimalField("Средний запас (руб)", max_digits=12, decimal_places=2, blank=True, null=True, db_index=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fb_turnover_use"
        verbose_name = "Turnover"
        verbose_name_plural = "Turnover inventories"

    def __str__(self):
        return self.nomenclature or f"Turnover {self.id}"


class TurnoverIndicator(models.Model):
    indicator = models.IntegerField(blank=True, null=False)
    date_start = models.DateField("Дата", blank=True, null=True, db_index=True)

    class Meta:
        db_table = "fb_turnover_ind"
        verbose_name = "Turnover target value"
        verbose_name_plural = "Turnover target values"

    def __str__(self):
        return str(self.indicator) if self.indicator is not None else f"Target value turnover {self.id}"





class AccreceivUse(models.Model):
    date_start = models.DateField("Дата начала", db_index=True)
    date_end = models.DateField("Дата окончания", db_index=True)

    partner = models.CharField("Контрагент", max_length=255, blank=True, null=True, db_index=True)
    contract_partner = models.CharField("Договор контрагента", max_length=255, blank=True, null=True, db_index=True)
    manager_name = models.CharField("ФИО инициатора", max_length=255, blank=True, null=True, db_index=True)

    mutual_instock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    mutual_comstock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    mutual_spenstock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    mutual_finstock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, db_index=True)

    initial_stock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    coming_stock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    spending_stock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, db_index=True)
    final_stock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fb_accreceiv_use"
        verbose_name = "Account receivable"
        verbose_name_plural = "Accounts receivable"

    def __str__(self):
        return self.partner or f"Account receivable {self.id}"


class AccreceivIndicator(models.Model):
    manager_name = models.CharField(
        "ФИО инициатора",
        max_length=255,
        blank=True,
        null=False,
    )

    class Meta:
        db_table = "fb_accreceiv_ind"
        verbose_name = "Account receivable manager"
        verbose_name_plural = "Account receivable managers"

    def __str__(self):
        return self.manager_name or f"Account receivable manager {self.id}"








class PlannedSales(models.Model):
    date = models.DateField("Дата", null=False, blank=False, db_index=True)
    level1 = models.CharField("Уровень 1", max_length=255, blank=True, null=True, db_index=True)
    level2 = models.CharField("Уровень 2", max_length=255, blank=True, null=True, db_index=True)
    level3 = models.CharField("Уровень 3", max_length=255, blank=True, null=True, db_index=True)
    fact = models.DecimalField("Факт", max_digits=14, decimal_places=2, blank=True, null=True)
    appg = models.DecimalField("АППГ", max_digits=14, decimal_places=2, blank=True, null=True)
    appg_slice = models.DecimalField("АППГ в срезе", max_digits=14, decimal_places=2, blank=True, null=True)
    id_directory = models.IntegerField("id", blank=True, null=True)
    date_add = models.DateTimeField("Дата добавления", auto_now_add=True)

    class Meta:
        db_table = "planned_sales"
        verbose_name = "Planned sale"
        verbose_name_plural = "Planned sales"
        indexes = [
            models.Index(fields=["date", "id_directory"], name="idx_planned_sales_key"),
        ]


class PlanSales(models.Model):
    date = models.DateField("Дата", null=False, blank=False, db_index=True)
    level1 = models.CharField("Уровень 1", max_length=255, blank=True, null=True, db_index=True)
    level2 = models.CharField("Уровень 2", max_length=255, blank=True, null=True, db_index=True)
    level3 = models.CharField("Уровень 3", max_length=255, blank=True, null=True, db_index=True)
    plan = models.DecimalField("План", max_digits=14, decimal_places=2, blank=True, null=True)
    projection_s = models.DecimalField("Проекция", max_digits=14, decimal_places=2, blank=True, null=True)
    id_directory = models.IntegerField("id", blank=True, null=True)
    date_add = models.DateTimeField("Дата добавления", auto_now_add=True)

    class Meta:
        db_table = "plan_sales"
        verbose_name = "Planned sale target value"
        verbose_name_plural = "Planned sale target values"
        indexes = [
            models.Index(fields=["date", "id_directory"], name="idx_plan_sales_key"),
        ]


class PlannedSalesDirectory(models.Model):
    level1 = models.CharField("Уровень 1", max_length=255, blank=True, null=True, db_index=True)
    draft2 = models.CharField("Исходник 2", max_length=255, blank=True, null=True, db_index=True)
    level2 = models.CharField("Уровень 2", max_length=255, blank=True, null=True, db_index=True)
    draft3 = models.CharField("Исходник 3", max_length=255, blank=True, null=True, db_index=True)
    level3 = models.CharField("Уровень 3", max_length=255, blank=True, null=True, db_index=True)

    class Meta:
        db_table = "planned_sales_directory"
        verbose_name = "Planned sale directory"
        verbose_name_plural = "Planned sales directory"





class DashSales(models.Model):
    criterion = models.CharField(max_length=2, db_index=True)
    date = models.DateField(db_index=True)

    partner = models.CharField(max_length=600, blank=True, null=True, db_index=True)
    partner_code = models.IntegerField(blank=True, null=True)
    partner_inn = models.CharField(max_length=255, blank=True, null=True)

    macrosegment = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    segment = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    manager = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    old_branch = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    old_branch_group = models.CharField(max_length=255, blank=True, null=True)

    macroregion = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    region_group = models.CharField(max_length=255, blank=True, null=True)
    region = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    consignee = models.CharField(max_length=600, blank=True, null=True)

    nom_view = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    nom_category = models.CharField(max_length=255, blank=True, null=True)
    nom_group = models.CharField(max_length=255, blank=True, null=True)
    nom = models.CharField(max_length=600, blank=True, null=True, db_index=True)
    nom_code = models.IntegerField(blank=True, null=True, db_index=True)

    type_doc = models.CharField(max_length=600, blank=True, null=True)

    quantity = models.DecimalField(max_digits=15, decimal_places=0, blank=True, null=True)
    cost = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    weight_total = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    revenue = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    con_segment = models.CharField(max_length=255, blank=True, null=True)
    con_manager = models.CharField(max_length=255, blank=True, null=True)
    con_branch = models.CharField(max_length=255, blank=True, null=True)
    con_branch_group = models.CharField(max_length=255, blank=True, null=True)
    con_inn = models.CharField(max_length=255, blank=True, null=True)
    con_region = models.CharField(max_length=255, blank=True, null=True)

    nom_hier_code = models.IntegerField(blank=True, null=True)
    nom_hier = models.CharField(max_length=255, blank=True, null=True)

    contract_initiator = models.CharField(max_length=255, blank=True, null=True)
    contract_project = models.CharField(max_length=255, blank=True, null=True)
    contract_fullname = models.CharField(max_length=255, blank=True, null=True)
    contract_industry = models.CharField(max_length=255, blank=True, null=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dash_sales"
        indexes = [
            models.Index(fields=["date"], name="idx_dash_sales_date"),
            models.Index(fields=["date", "partner"], name="idx_dash_sales_date_partner"),
            models.Index(fields=["date", "nom"], name="idx_dash_sales_date_nom"),
        ]




class FBPurchasesRaw(models.Model):
    date_1C = models.DateField(db_index=True)

    quantity_1C_110 = models.DecimalField(max_digits=15, decimal_places=0, blank=True, null=True)
    revenue_1C_110 = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    VAT_1C_110 = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    quantity_1C_112 = models.DecimalField(max_digits=15, decimal_places=0, blank=True, null=True)
    revenue_1C_112 = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    VAT_1C_112 = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    quantity_1C_100753 = models.DecimalField(max_digits=15, decimal_places=0, blank=True, null=True)
    revenue_1C_100753 = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    VAT_1C_100753 = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    date_draft = models.DateField(db_index=True)

    party_status = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    partner = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    nomenclature = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fb_purchases_raw"
        verbose_name = "Purchases raw"
        verbose_name_plural = "Purchases raw"
        indexes = [
            models.Index(fields=["date_1C"], name="idx_fb_purch_raw_date_1c"),
            models.Index(fields=["date_draft"], name="idx_fb_purch_raw_draft"),
        ]



class TurnoverRaw(models.Model):
    date_stock = models.DateField(db_index=True)
    date_start = models.DateField(db_index=True)
    date_end = models.DateField(db_index=True)

    warehouse_group = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    warehouse = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    nomenclature = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    quantity = models.CharField(max_length=255, blank=True, null=True)
    price = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    amount_day = models.IntegerField(blank=True, null=True)

    middle_stock = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, db_index=True)
    middle_rubstock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, db_index=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fb_turnover_raw"
        verbose_name = "Turnover raw"
        verbose_name_plural = "Turnover raw"
        indexes = [
            models.Index(fields=["date_stock"], name="idx_turn_raw_stock"),
            models.Index(fields=["date_start"], name="idx_turn_raw_start"),
            models.Index(fields=["date_end"], name="idx_turn_raw_end"),
        ]

    def __str__(self):
        return self.nomenclature or f"Turnover raw {self.id}"




class AccreceivRaw(models.Model):
    date_start = models.DateField(db_index=True)
    date_end = models.DateField(db_index=True)

    partner = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    contract_partner = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    manager_name = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    mutual_instock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    mutual_comstock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    mutual_spenstock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    mutual_finstock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, db_index=True)

    initial_stock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    coming_stock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    spending_stock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, db_index=True)
    final_stock = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fb_accreceiv_raw"
        verbose_name = "Account receivable raw"
        verbose_name_plural = "Accounts receivable raw"
        indexes = [
            models.Index(fields=["date_start"], name="idx_accr_raw_start"),
            models.Index(fields=["date_end"], name="idx_accr_raw_end"),
            models.Index(fields=["manager_name"], name="idx_accr_raw_manager"),
        ]

    def __str__(self):
        return self.partner or f"Account receivable raw {self.id}"







#МОДЕЛИ ПАРСЕРОВ


class DepartureDiscount(models.Model):
    product_key = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key",
    )

    departure = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Производство",
    )

    arrival = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Регион продажи",
        help_text="Для legacy-строк может быть пустым",
    )

    distr = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        verbose_name="Скидка distr",
    )

    distr_1 = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        verbose_name="Скидка distr_1",
    )

    small = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        verbose_name="Скидка small",
    )

    medium = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        verbose_name="Скидка medium",
    )

    large = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        verbose_name="Скидка large",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активная запись",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "departure_discount"
        verbose_name = "Скидка по производству"
        verbose_name_plural = "Скидки по производствам"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "product_key",
                    "departure",
                    "arrival",
                ],
                condition=Q(is_active=True),
                name="uniq_active_dep_discount_product_route",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_active=False)
                    | Q(arrival__isnull=False)
                ),
                name="active_dep_discount_requires_arrival",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "product_key",
                    "departure",
                    "arrival",
                    "is_active",
                ],
                name="dep_disc_route_active_idx",
            ),
            models.Index(
                fields=[
                    "product_key",
                    "departure",
                    "arrival",
                    "date_add",
                ],
                name="dep_disc_route_date_idx",
            ),
        ]

    def __str__(self):
        active_text = (
            "active"
            if self.is_active
            else "inactive"
        )

        return (
            f"{self.product_key} | "
            f"{self.departure} -> "
            f"{self.arrival or 'legacy'} | "
            f"{active_text}"
        )



class ParserPrefix(models.Model):
    source = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Источник",
    )

    prefix = models.CharField(
        max_length=255,
        verbose_name="Префикс",
    )

    shipp_region = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Регион",
        null=True,
        blank=True,
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "parser_prefix"
        verbose_name = "Parser: prefix"
        verbose_name_plural = "Parser: prefixes"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "prefix"],
                name="parser_prefix_source_prefix_unique",
            )
        ]

    def __str__(self):
        return f"{self.source}: {self.prefix} -> {self.shipp_region}"


class ParserProductUrl(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"

    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
    )

    source = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Источник",
    )

    prefix = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Префикс",
    )

    url = models.URLField(
        max_length=1000,
        verbose_name="URL с префиксом",
    )

    additional_property = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Дополнительное свойство",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        verbose_name="Статус",
    )

    lastmod = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Lastmod из sitemap",
    )

    is_loaded = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Загружено",
    )

    last_error = models.TextField(
        blank=True,
        null=True,
        verbose_name="Последняя ошибка",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    date_update = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        db_table = "parser_product_url"
        verbose_name = "Parser: Product URL"
        verbose_name_plural = "Parser: Product URLs"
        indexes = [
            models.Index(fields=["source", "status"]),
            models.Index(fields=["source", "is_loaded"]),
            models.Index(fields=["source", "date_update"]),
            models.Index(fields=["url"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "url", "additional_property"],
                nulls_distinct=False,
                name="parser_product_url_source_url_additional_unique",
            )
        ]

    def __str__(self):
        return f"{self.source}: {self.url}"


class ParserProductProperty(models.Model):
    source = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Источник",
    )

    product_key = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key",
    )

    url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="URL",
    )

    properties = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Свойство",
    )

    value = models.TextField(
        blank=True,
        null=True,
        verbose_name="Значение",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "parser_product_property"
        verbose_name = "Parser: product property"
        verbose_name_plural = "Parser: product properties"
        indexes = [
            models.Index(fields=["source", "product_key"]),
            models.Index(fields=["product_key"]),
        ]

    def __str__(self):
        return f"{self.source}: {self.product_key} / {self.properties}"


class TaraProductPrice(models.Model):
    product_key = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key",
    )

    url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="URL",
    )

    properties_price = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Интервал цены",
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Цена",
    )

    value_added_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="НДС",
    )

    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Цена без НДС",
    )

    color = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Цвет",
    )

    image = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="Изображение",
    )

    special_quantity = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Спец. количество",
    )

    category = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Категория",
    )

    name = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="Наименование",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "tara_product_price"
        verbose_name = "Parser: Tara price"
        verbose_name_plural = "Parser: Tara prices"
        indexes = [
            models.Index(fields=["product_key"]),
            models.Index(fields=["product_key", "date_add"]),
        ]

    def __str__(self):
        return f"{self.product_key}: {self.name}"




class PsProductPrice(models.Model):
    product_key = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key",
    )

    url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="URL",
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Цена",
    )

    value_added_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="НДС",
    )

    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Цена без НДС",
    )

    discount = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Скидка в карточке товара",
    )

    color = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Цвет",
    )

    image = models.TextField(
        blank=True,
        null=True,
        verbose_name="Изображение",
    )

    name = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="Наименование товара",
    )

    properties_price = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Свойства цены",
    )

    special_quantity = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Персональные условия",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "ps_product_price"
        verbose_name = "Parser: PS price"
        verbose_name_plural = "Parser: PS prices"
        indexes = [
            models.Index(fields=["product_key"]),
            models.Index(fields=["product_key", "date_add"]),
        ]

    def __str__(self):
        return f"{self.product_key}: {self.name}"




class TtProductPrice(models.Model):
    product_key = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key",
    )

    url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="URL",
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Цена",
    )

    value_added_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="НДС",
    )

    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Цена без НДС",
    )

    additional_property = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Дополнительное свойство",
    )

    image = models.TextField(
        blank=True,
        null=True,
        verbose_name="Изображение",
    )

    name = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="Наименование товара",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "tt_product_price"
        verbose_name = "Parser: TT price"
        verbose_name_plural = "Parser: TT prices"
        indexes = [
            models.Index(fields=["product_key"]),
            models.Index(fields=["product_key", "date_add"]),
        ]

    def __str__(self):
        return f"{self.product_key}: {self.name}"




class ParserProductMatch(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"

    STATUS_CHOICES = (
        (
            STATUS_ACTIVE,
            "Активен",
        ),
        (
            STATUS_INACTIVE,
            "Неактивен",
        ),
    )

    MATCH_TYPE_MANUAL = "manual"
    MATCH_TYPE_AUTO = "auto"

    MATCH_TYPE_CHOICES = (
        (
            MATCH_TYPE_MANUAL,
            "Добавлен вручную",
        ),
        (
            MATCH_TYPE_AUTO,
            "Добавлен автоматически",
        ),
    )

    product_key_base = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key нашего товара",
    )

    product_key_competitor = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key конкурента",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        verbose_name="Статус",
    )

    match_type = models.CharField(
        max_length=20,
        choices=MATCH_TYPE_CHOICES,
        default=MATCH_TYPE_MANUAL,
        db_index=True,
        verbose_name="Способ добавления",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "parser_product_match"

        verbose_name = "Parser: product matching"
        verbose_name_plural = "Parser: product matches"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "product_key_base",
                    "product_key_competitor",
                ],
                name=(
                    "parser_product_match_"
                    "base_competitor_uniq"
                ),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "product_key_base",
                    "status",
                ],
                name=(
                    "parser_match_base_status_idx"
                ),
            ),
            models.Index(
                fields=[
                    "product_key_competitor",
                    "status",
                ],
                name=(
                    "parser_match_comp_status_idx"
                ),
            ),
            models.Index(
                fields=[
                    "match_type",
                    "status",
                ],
                name=(
                    "parser_match_type_status_idx"
                ),
            ),
        ]

    def __str__(self):
        return (
            f"{self.product_key_base} "
            f"→ {self.product_key_competitor} "
            f"[{self.match_type}; {self.status}]"
        )



class IPriceCompetitorSelectionOverride(models.Model):
    MODE_AUTO = "auto"
    MODE_INCLUDE = "include"
    MODE_EXCLUDE = "exclude"

    MODE_CHOICES = (
        (MODE_AUTO, "Автоматический выбор"),
        (MODE_INCLUDE, "Включён вручную"),
        (MODE_EXCLUDE, "Исключён вручную"),
    )

    product_key_base = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key нашего товара",
    )
    product_key_competitor = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key конкурента",
    )
    selection_mode = models.CharField(
        max_length=20,
        choices=MODE_CHOICES,
        default=MODE_AUTO,
        db_index=True,
        verbose_name="Режим участия в расчёте",
    )
    reason = models.TextField(
        blank=True,
        default="",
        verbose_name="Причина ручного решения",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="iprice_competitor_selection_overrides",
        verbose_name="Кем изменено",
    )
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "iprice_competitor_selection_override"
        verbose_name = "iPrice: ручной выбор конкурента"
        verbose_name_plural = "iPrice: ручной выбор конкурентов"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "product_key_base",
                    "product_key_competitor",
                ],
                name="iprice_competitor_selection_pair_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["product_key_base", "selection_mode"],
                name="iprice_comp_sel_base_mode_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.product_key_base} -> "
            f"{self.product_key_competitor}: {self.selection_mode}"
        )


class IPriceCompetitorSelectionChange(models.Model):
    override = models.ForeignKey(
        IPriceCompetitorSelectionOverride,
        on_delete=models.PROTECT,
        related_name="changes",
        verbose_name="Настройка конкурента",
    )
    snapshot = models.ForeignKey(
        "IPriceSnapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="competitor_selection_changes",
        verbose_name="Снапшот",
    )
    previous_mode = models.CharField(max_length=20, blank=True, default="")
    selection_mode = models.CharField(
        max_length=20,
        choices=IPriceCompetitorSelectionOverride.MODE_CHOICES,
    )
    reason = models.TextField(blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="iprice_competitor_selection_changes",
    )
    date_add = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "iprice_competitor_selection_change"
        ordering = ("-date_add", "-id")
        indexes = [
            models.Index(
                fields=["snapshot", "date_add"],
                name="iprice_comp_change_snap_idx",
            ),
        ]


class BaseProductPrice(models.Model):
    product_key = models.BigIntegerField(db_index=True, verbose_name="Product key")

    url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="URL",
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Цена",
    )

    value_added_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="НДС",
    )

    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Цена без НДС",
    )

    color = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Цвет",
    )

    image = models.TextField(
        blank=True,
        null=True,
        verbose_name="Изображение",
    )

    name = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name="Наименование товара",
    )

    code_1c = models.BigIntegerField(
        blank=True,
        null=True,
        db_index=True,
        verbose_name="ID товара в 1С",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "base_product_price"
        verbose_name = "Parser: Base price"
        verbose_name_plural = "Parser: Base prices"
        indexes = [
            models.Index(fields=["product_key"]),
            models.Index(fields=["product_key", "date_add"]),
            models.Index(fields=["code_1c"]),
        ]

    def __str__(self):
        return f"{self.product_key}: {self.name}"




class ParserProductClassification(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"

    STATUS_CHOICES = (
        (
            STATUS_ACTIVE,
            "Активен",
        ),
        (
            STATUS_INACTIVE,
            "Неактивен",
        ),
    )

    ITEM_TYPE_PRODUCT = "product"
    ITEM_TYPE_COMPONENT = "component"

    ITEM_TYPE_CHOICES = (
        (
            ITEM_TYPE_PRODUCT,
            "Товар",
        ),
        (
            ITEM_TYPE_COMPONENT,
            "Комплектующее",
        ),
    )

    product_key = models.BigIntegerField(
        unique=True,
        db_index=True,
        verbose_name="Product key",
    )

    category = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Категория",
    )

    subcategory = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Подкатегория",
    )

    subcategory_type = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Тип подкатегории",
    )

    material = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Материал",
    )

    color = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Цвет",
    )

    modification = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Модификация",
    )

    article_number_analogs = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Артикул группы аналогов",
    )

    item_type = models.CharField(
        max_length=20,
        choices=ITEM_TYPE_CHOICES,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Тип товара",
    )

    url = models.TextField(
        blank=True,
        null=True,
        verbose_name="URL",
    )

    image = models.TextField(
        blank=True,
        null=True,
        verbose_name="Изображение",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        verbose_name="Статус",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    date_update = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Дата изменения",
    )

    class Meta:
        db_table = "parser_product_classification"

        verbose_name = (
            "Parser: product classification"
        )

        verbose_name_plural = (
            "Parser: products classification"
        )

    def __str__(self):
        return f"{self.product_key} [{self.status}]"








class YdWordstatPhraseRef(models.Model):
    feature = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    category = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    phrase = models.CharField(max_length=255, unique=True, db_index=True)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_ref"
        verbose_name = "YD Wordstat phrase ref"
        verbose_name_plural = "YD Wordstat phrase refs"
        indexes = [
            models.Index(fields=["feature", "category"]),
            models.Index(fields=["category", "phrase"]),
        ]

    def __str__(self):
        return self.phrase


class YdWordstatDeviceRef(models.Model):
    device = models.CharField(max_length=255, unique=True, db_index=True)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_ref_device"
        verbose_name = "YD Wordstat device ref"
        verbose_name_plural = "YD Wordstat device refs"

    def __str__(self):
        return self.device


class YdWordstatIplastRegionRef(models.Model):
    region_value = models.IntegerField(unique=True, db_index=True)
    macroregion_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_ref_iplast"
        verbose_name = "YD Wordstat Iplast region ref"
        verbose_name_plural = "YD Wordstat Iplast region refs"
        indexes = [
            models.Index(fields=["macroregion_label"]),
        ]

    def __str__(self):
        return f"{self.region_value} → {self.macroregion_label}"


class YdWordstatAllRaw(models.Model):
    phrase = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    date = models.DateField(blank=True, null=True, db_index=True)
    count = models.BigIntegerField(blank=True, null=True)

    feature = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    category = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_all"
        verbose_name = "YD Wordstat all raw"
        verbose_name_plural = "YD Wordstat all raw"
        indexes = [
            models.Index(fields=["phrase", "date"]),
            models.Index(fields=["feature", "category", "phrase"]),
            models.Index(fields=["date", "phrase"]),
        ]

    def __str__(self):
        return f"{self.phrase} {self.date}: {self.count}"


class YdWordstatDeviceRaw(models.Model):
    phrase = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    device = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    date = models.DateField(blank=True, null=True, db_index=True)
    count = models.BigIntegerField(blank=True, null=True)

    feature = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    category = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_device"
        verbose_name = "YD Wordstat device raw"
        verbose_name_plural = "YD Wordstat device raw"
        indexes = [
            models.Index(fields=["phrase", "device", "date"]),
            models.Index(fields=["device", "date"]),
            models.Index(fields=["feature", "category", "phrase"]),
        ]

    def __str__(self):
        return f"{self.phrase} {self.device} {self.date}: {self.count}"


class YdWordstatIplastRaw(models.Model):
    """A monthly v2 result aggregated by the API over one IPLAST region set."""

    phrase = models.CharField(max_length=255)
    macroregion_label = models.CharField(max_length=255)
    group_fingerprint = models.CharField(max_length=64)
    date = models.DateField()
    count = models.BigIntegerField()
    feature = models.CharField(max_length=255, blank=True, null=True)
    category = models.CharField(max_length=255, blank=True, null=True)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_iplast_api"
        constraints = [models.UniqueConstraint(
            fields=["phrase", "macroregion_label", "date"], name="wordstat_iplast_month_unique",
        )]


class YdWordstatApiCheckpoint(models.Model):
    source = models.CharField(max_length=16)
    phrase = models.CharField(max_length=255)
    dimension = models.CharField(max_length=255, default="")
    fingerprint = models.CharField(max_length=64)
    date_start = models.DateField()
    date_finish = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "yd_wordstat_api_checkpoint"
        constraints = [models.UniqueConstraint(
            fields=["source", "phrase", "dimension"], name="wordstat_checkpoint_unique",
        )]


class YdWordstatApiQuota(models.Model):
    """Shared rolling request budget; retained across workers and restarts."""

    scope = models.CharField(max_length=64, primary_key=True)
    requests = models.JSONField(default=list)
    blocked_until = models.FloatField(default=0)

    class Meta:
        db_table = "yd_wordstat_api_quota"








class RevenueSales(models.Model):
    date = models.DateField("Дата", db_index=True)

    direction = models.CharField("Направление", max_length=255, blank=True, null=True, db_index=True)
    project = models.CharField("Проект", max_length=255, blank=True, null=True, db_index=True)

    manager = models.CharField("Менеджер", max_length=255, blank=True, null=True, db_index=True)
    partner = models.CharField("Контрагент", max_length=600, blank=True, null=True, db_index=True)
    consignee = models.CharField("Грузополучатель", max_length=600, blank=True, null=True, db_index=True)
    partner_code = models.IntegerField(blank=True, null=True, db_index=True)

    nom_view = models.CharField("Вид продукции", max_length=255, blank=True, null=True, db_index=True)
    nom_category = models.CharField("Категория", max_length=255, blank=True, null=True, db_index=True)
    nom_group = models.CharField("Группа", max_length=255, blank=True, null=True, db_index=True)
    nom = models.CharField("Номенклатура", max_length=600, blank=True, null=True, db_index=True)
    nom_code = models.IntegerField("Код номенклатуры", blank=True, null=True, db_index=True)

    nom_hier = models.CharField(
        "Номенклатура (группировка)",
        max_length=600,
        blank=True,
        null=True,
        db_index=True,
    )

    type_doc = models.CharField("Документ-регистратор", max_length=600, blank=True, null=True, db_index=True)

    quantity = models.DecimalField(max_digits=15, decimal_places=0, blank=True, null=True)
    weight_total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    revenue = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    is_new_sku = models.BooleanField(default=False)
    is_new_client = models.BooleanField(default=False)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "revenue_sales"
        indexes = [
            models.Index(fields=["date"], name="idx_rev_sales_date"),
            models.Index(fields=["date", "direction"], name="idx_rev_sales_dir"),
            models.Index(fields=["date", "project"], name="idx_rev_sales_proj"),
            models.Index(fields=["date", "partner"], name="idx_rev_sales_partner"),
            models.Index(fields=["date", "nom_code"], name="idx_rev_sales_nom_code"),
        ]




class Nomenclature(models.Model):
    nom_code = models.IntegerField(
        db_index=True,
        verbose_name="Код номенклатуры",
    )

    nom = models.CharField(
        blank=True,
        null=True,
        verbose_name="Наименование номенклатуры",
    )

    nom_article = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Артикул номенклатуры",
    )

    nom_base_unit = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Базовая единица",
    )

    nom_stock_unit = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Единица хранения остатков",
    )

    nom_report_unit = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Единица для отчетов",
    )

    nom_cn_fea = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Код ТН ВЭД",
    )

    full_nom = models.CharField(
        blank=True,
        null=True,
        verbose_name="Полное наименование",
    )

    weight_kg = models.DecimalField(
        max_digits=9,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Вес, кг",
    )

    weight_assembly_kg = models.DecimalField(
        max_digits=9,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Вес изделия в сборе, кг",
    )

    nom_view = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Вид номенклатуры",
    )

    nom_group = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Группа продукции",
    )

    nom_hier_code = models.IntegerField(
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Код группировки",
    )

    nom_hier = models.CharField(
        blank=True,
        null=True,
        verbose_name="Группировка",
    )

    nom_category = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Категория продукции",
    )

    vat = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="НДС",
    )

    type_rep = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Вид воспроизводства",
    )

    height_mm = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Высота, мм",
    )

    length_mm = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Длина, мм",
    )

    width_mm = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Ширина, мм",
    )

    tiering = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Ярусность",
    )

    color = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Цвет",
    )

    quantity_eurotruck = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Количество в еврофуре",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "nomenclature"
        verbose_name = "Номенклатура"
        verbose_name_plural = "Номенклатура"

    def __str__(self):
        return f"{self.nom_code} - {self.nom}"



class NomenclaturePrice(models.Model):
    date = models.DateField(
        db_index=True,
        verbose_name="Дата цены",
    )

    shipp_region = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Регион отгрузки",
    )

    nom_group = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Группа номенклатуры",
    )

    price_list = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Прайс-лист",
    )

    nom = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Номенклатура",
    )

    code = models.IntegerField(
        db_index=True,
        verbose_name="Код номенклатуры",
    )

    vat = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="НДС",
    )

    distr = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name="Дистрибьютор",
    )

    distr_1 = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name="Дистрибьютор 1",
    )

    retail = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name="Розница",
    )

    small = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name="Малый опт",
    )

    medium = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name="Средний опт",
    )

    large = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name="Крупный опт",
    )

    base = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name="Базовая цена",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "nomenclature_price"
        verbose_name = "Цена номенклатуры"
        verbose_name_plural = "Цены номенклатуры"

        indexes = [
            models.Index(
                fields=["date", "code"],
                name="nom_price_date_code_idx",
            ),
            models.Index(
                fields=["date", "shipp_region"],
                name="nom_price_date_region_idx",
            ),
        ]

    def __str__(self):
        return f"{self.date} | {self.code} | {self.shipp_region}"


class TransportCost(models.Model):
    departure = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Пункт отправления",
    )

    arrival = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Пункт прибытия",
    )

    cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name="Стоимость перевозки без НДС",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активная запись",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "transport_cost"
        verbose_name = "Транспортные расходы"
        verbose_name_plural = "Транспортные расходы"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "departure",
                    "arrival",
                ],
                condition=Q(is_active=True),
                name="uniq_active_transport_departure_arrival",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "departure",
                    "arrival",
                    "is_active",
                ],
                name="transport_route_active_idx",
            ),
            models.Index(
                fields=[
                    "departure",
                    "arrival",
                    "date_add",
                ],
                name="transport_route_date_idx",
            ),
        ]

    def __str__(self):
        active_text = (
            "active"
            if self.is_active
            else "inactive"
        )

        return (
            f"{self.departure} -> "
            f"{self.arrival}: "
            f"{self.cost} "
            f"({active_text})"
        )


class ProductCost(models.Model):
    date = models.DateField(
        db_index=True,
        verbose_name="Месяц",
    )

    code = models.IntegerField(
        db_index=True,
        verbose_name="Код номенклатуры",
    )

    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Наименование",
    )

    departure = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Пункт отправления",
    )

    cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        verbose_name="Себестоимость",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    class Meta:
        db_table = "product_cost"
        verbose_name = "Себестоимость"
        verbose_name_plural = "Себестоимость"

        constraints = [
            models.UniqueConstraint(
                fields=["date", "code", "departure"],
                name="product_cost_month_code_departure_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.date} | {self.code} | {self.departure} | {self.cost}"


class IPriceCalculationConfig(models.Model):
    product_key = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key",
    )

    departure = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Место производства",
    )

    arrival = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Регион продажи",
    )

    base_analog = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name="Коэффициент цены аналога",
        help_text=(
            "Коэффициент, на который умножается "
            "цена аналога или конкурента"
        ),
    )

    base_exclusive = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name="Маржинальность эксклюзивного товара",
        help_text=(
            "Используется при расчете цены от себестоимости: "
            "РРЦ = себестоимость с логистикой / "
            "(1 - base_exclusive)"
        ),
    )

    minimum_margin = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name="Минимальная маржинальность",
        help_text=(
            "Минимально допустимая маржинальность "
            "после применения скидки"
        ),
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активная конфигурация",
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )


    class Meta:
        db_table = "iprice_calculation_config"

        verbose_name = "Конфигурация расчета iPrice"
        verbose_name_plural = "Конфигурации расчета iPrice"

        ordering = (
            "product_key",
            "departure",
            "arrival",
            "-date_add",
            "-id",
        )

        constraints = (
            models.UniqueConstraint(
                fields=(
                    "product_key",
                    "departure",
                    "arrival",
                ),
                condition=Q(
                    is_active=True,
                ),
                name=(
                    "unique_active_iprice_config_"
                    "per_product_route"
                ),
            ),
            models.CheckConstraint(
                condition=Q(
                    base_analog__gte=0,
                ),
                name=(
                    "iprice_config_base_analog_gte_zero"
                ),
            ),
            models.CheckConstraint(
                condition=(
                    Q(base_exclusive__gt=0)
                    & Q(base_exclusive__lt=1)
                ),
                name=(
                    "iprice_config_base_exclusive_range"
                ),
            ),
            models.CheckConstraint(
                condition=(
                    Q(minimum_margin__gte=0)
                    & Q(minimum_margin__lt=1)
                ),
                name=(
                    "iprice_config_minimum_margin_range"
                ),
            ),
        )

        indexes = (
            models.Index(
                fields=(
                    "product_key",
                    "departure",
                    "arrival",
                    "date_add",
                ),
                name="iprice_config_route_date_idx",
            ),
        )

    def __str__(self):
        active_text = (
            "active"
            if self.is_active
            else "inactive"
        )

        return (
            f"{self.product_key}: "
            f"{self.departure} -> {self.arrival}, "
            f"analog={self.base_analog}, "
            f"exclusive={self.base_exclusive}, "
            f"margin={self.minimum_margin} "
            f"({active_text})"
        )


class ParserMasterPipelineRun(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_WAITING_TARA = "waiting_tara"
    STATUS_WAITING_SESSION = "waiting_session"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_WAITING_TARA, "Waiting for Tara"),
        (STATUS_WAITING_SESSION, "Waiting for session"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
    )

    current_step = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="parser_master_pipeline_runs",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    error = models.TextField(
        blank=True,
        default="",
    )

    result = models.JSONField(
        default=dict,
        blank=True,
    )

    date_add = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "parser_master_pipeline_run"
        ordering = ["-date_add"]

    def __str__(self):
        return f"Parser pipeline #{self.pk}: {self.status}"




class IPriceSnapshot(models.Model):
    STATUS_BUILDING = "building"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (
            STATUS_BUILDING,
            "Выполняется",
        ),
        (
            STATUS_SUCCESS,
            "Рассчитан",
        ),
        (
            STATUS_FAILED,
            "Ошибка",
        ),
    )

    calculation_date = models.DateField(
        db_index=True,
        verbose_name="Дата расчета",
    )

    version_number = models.PositiveIntegerField(
        unique=True,
        db_index=True,
        verbose_name="Глобальный номер версии",
    )

    revision_for_date = models.PositiveIntegerField(
        verbose_name="Номер версии за дату",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_BUILDING,
        db_index=True,
        verbose_name="Статус",
    )

    is_current = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Текущая версия за дату",
    )

    is_active = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Активный окончательный расчет",
    )

    was_active = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Была активной",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_iprice_snapshots",
        verbose_name="Кем создан",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата создания",
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата завершения",
    )

    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activated_iprice_snapshots",
        verbose_name="Кем активирован",
    )

    activated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата активации",
    )

    error = models.TextField(
        blank=True,
        default="",
        verbose_name="Ошибка",
    )

    parameters = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Параметры запуска",
    )

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iprice_snapshot"
        verbose_name = "iPrice snapshot"
        verbose_name_plural = "iPrice snapshots"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "calculation_date",
                    "revision_for_date",
                ],
                name="iprice_snapshot_date_revision_uniq",
            ),
            models.UniqueConstraint(
                fields=[
                    "calculation_date",
                ],
                condition=Q(is_current=True),
                name="iprice_snapshot_current_date_uniq",
            ),
            models.UniqueConstraint(
                fields=[
                    "is_active",
                ],
                condition=Q(is_active=True),
                name="iprice_snapshot_one_active_uniq",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "calculation_date",
                    "is_current",
                ],
                name="iprice_snap_date_current_idx",
            ),
            models.Index(
                fields=[
                    "status",
                    "created_at",
                ],
                name="iprice_snap_status_created_idx",
            ),
        ]

        ordering = [
            "-created_at",
            "-id",
        ]

    @property
    def display_version(self):
        return (
            f"v{self.version_number}-"
            f"{self.calculation_date:%d.%m.%y}"
        )

    def __str__(self):
        return self.display_version


class IPriceSnapshotProduct(models.Model):
    PRICING_METHOD_ANALOG = "analog"
    PRICING_METHOD_EXCLUSIVE = "exclusive"

    PRICING_METHOD_CHOICES = (
        (
            PRICING_METHOD_ANALOG,
            "Аналог",
        ),
        (
            PRICING_METHOD_EXCLUSIVE,
            "Эксклюзив",
        ),
    )

    STATUS_SUCCESS = "success"
    STATUS_WARNING = "warning"
    STATUS_ERROR = "error"

    STATUS_CHOICES = (
        (
            STATUS_SUCCESS,
            "Рассчитано",
        ),
        (
            STATUS_WARNING,
            "Есть предупреждения",
        ),
        (
            STATUS_ERROR,
            "Расчет невозможен",
        ),
    )

    snapshot = models.ForeignKey(
        IPriceSnapshot,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Snapshot",
    )

    base_product_key = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key нашего товара",
    )

    code_1c = models.BigIntegerField(
        db_index=True,
        verbose_name="Код номенклатуры 1С",
    )

    nom = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name="Наименование",
    )

    nom_hier_code = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Код иерархии",
    )

    nom_hier = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name="Иерархия",
    )

    nom_view = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Вид номенклатуры",
    )

    nom_category = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Категория номенклатуры",
    )

    nom_group = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Группа номенклатуры",
    )

    assortment_matrix_status = models.TextField(
        null=True,
        blank=True,
        verbose_name="САМ",
    )

    our_offer = models.TextField(
        null=True,
        blank=True,
        verbose_name="Наши предложения",
    )

    category = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Внутренняя категория",
    )

    subcategory = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Внутренняя подкатегория",
    )

    subcategory_type = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Тип подкатегории",
    )

    color = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Цвет",
    )

    material = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Материал",
    )

    modification = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Модификация",
    )

    image = models.TextField(
        null=True,
        blank=True,
        verbose_name="Изображение",
    )

    url = models.TextField(
        null=True,
        blank=True,
        verbose_name="URL",
    )

    item_type = models.CharField(
        max_length=20,
        db_index=True,
        verbose_name="Тип позиции",
    )

    pricing_method = models.CharField(
        max_length=20,
        choices=PRICING_METHOD_CHOICES,
        db_index=True,
        verbose_name="Метод ценообразования",
    )

    competitor_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество конкурентов",
    )

    competitor_rrp_min = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Минимальная РРЦ конкурентов",
    )

    competitor_rrp_max = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Максимальная РРЦ конкурентов",
    )

    competitor_rrp_median = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Медианная РРЦ конкурентов",
    )

    current_retail_min = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Минимальная текущая розница",
    )

    current_retail_max = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Максимальная текущая розница",
    )

    current_retail_median = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Медианная текущая розница",
    )

    current_vs_competitor_amount = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Отклонение от медианы, руб.",
    )

    current_vs_competitor_percent = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Отклонение от медианы, доля",
    )

    effective_approved_rrp_median = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Медиана итоговой РРЦ",
    )

    current_vs_approved_amount = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Разница розницы и итоговой РРЦ",
    )

    calculation_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SUCCESS,
        db_index=True,
        verbose_name="Статус расчета",
    )

    warning_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Предупреждения",
    )

    error_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Ошибки",
    )

    calculation_details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Детали расчета",
    )

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iprice_snapshot_product"
        verbose_name = "iPrice snapshot product"
        verbose_name_plural = "iPrice snapshot products"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "snapshot",
                    "base_product_key",
                ],
                name="iprice_snap_product_key_uniq",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "snapshot",
                    "code_1c",
                ],
                name="iprice_sp_snap_code_idx",
            ),
            models.Index(
                fields=[
                    "snapshot",
                    "pricing_method",
                ],
                name="iprice_sp_snap_method_idx",
            ),
            models.Index(
                fields=[
                    "snapshot",
                    "calculation_status",
                ],
                name="iprice_sp_snap_status_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.snapshot.display_version} | "
            f"{self.code_1c} | {self.nom}"
        )


class IPriceSnapshotCompetitor(models.Model):
    snapshot_product = models.ForeignKey(
        IPriceSnapshotProduct,
        on_delete=models.CASCADE,
        related_name="competitors",
        verbose_name="Товар snapshot",
    )

    competitor_product_key = models.BigIntegerField(
        db_index=True,
        verbose_name="Product key конкурента",
    )

    source = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Источник",
    )

    url = models.TextField(
        null=True,
        blank=True,
        verbose_name="URL конкурента",
    )

    prefix = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Префикс",
    )

    competitor_price_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Дата конкурентной цены",
    )

    competitor_final_price_max = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Максимальная цена без НДС",
    )

    source_price_row_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID выбранной строки цены",
    )

    price_variants = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Все варианты цены за день",
    )

    is_all_regions = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Применяется ко всем регионам",
    )

    applicable_regions = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Применимые регионы продажи",
    )

    base_analog = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Коэффициент аналога",
    )

    preliminary_rrp = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Предварительная РРЦ",
    )

    calculation_status = models.CharField(
        max_length=20,
        default="success",
        db_index=True,
        verbose_name="Статус расчета",
    )

    warning_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Предупреждения",
    )

    error_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Ошибки",
    )

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iprice_snapshot_competitor"
        verbose_name = "iPrice snapshot competitor"
        verbose_name_plural = "iPrice snapshot competitors"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "snapshot_product",
                    "competitor_product_key",
                ],
                name="iprice_snap_product_competitor_uniq",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "snapshot_product",
                    "source",
                ],
                name="iprice_sc_product_source_idx",
            ),
            models.Index(
                fields=[
                    "source",
                    "competitor_product_key",
                    "competitor_price_date",
                ],
                name="iprice_sc_source_key_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.snapshot_product.base_product_key} -> "
            f"{self.source}:{self.competitor_product_key}"
        )


class IPriceSnapshotRegion(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_WARNING = "warning"
    STATUS_ERROR = "error"

    snapshot_product = models.ForeignKey(
        IPriceSnapshotProduct,
        on_delete=models.CASCADE,
        related_name="regions",
        verbose_name="Товар snapshot",
    )

    sale_region = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Регион продажи",
    )

    departure = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="Производство",
    )

    product_cost_source_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID исходной себестоимости",
    )

    transport_cost_source_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID исходного транспорта",
    )

    nomenclature_price_source_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID исходной цены 1С",
    )

    departure_discount_source_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID исходных скидок",
    )

    calculation_config_source_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID исходной конфигурации",
    )

    product_cost_month = models.DateField(
        null=True,
        blank=True,
        verbose_name="Месяц себестоимости",
    )

    nomenclature_price_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата цены 1С",
    )

    current_retail = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Текущая розница",
    )

    current_distr = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Текущий distr",
    )

    current_distr_1 = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Текущий distr_1",
    )

    current_small = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Текущий малый опт",
    )

    current_medium = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Текущий средний опт",
    )

    current_large = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Текущий крупный опт",
    )

    product_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Себестоимость",
    )

    transport_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Стоимость перевозки",
    )

    quantity_eurotruck = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Количество в еврофуре",
    )

    logistics_unit = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Логистика на единицу",
    )

    cost_with_logistics = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Себестоимость с логистикой",
    )

    regional_competitor_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество конкурентов региона",
    )

    regional_competitor_rrp_min = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Минимальная РРЦ конкурентов региона",
    )

    regional_competitor_rrp_max = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Максимальная РРЦ конкурентов региона",
    )

    regional_competitor_rrp_median = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Медианная РРЦ конкурентов региона",
    )

    base_analog = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Коэффициент аналога",
    )

    base_exclusive = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Коэффициент эксклюзива",
    )

    minimum_margin = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Минимальная маржинальность",
    )

    discount_distr = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Скидка distr",
    )

    discount_distr_1 = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Скидка distr_1",
    )

    discount_small = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Скидка small",
    )

    discount_medium = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Скидка medium",
    )

    discount_large = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Скидка large",
    )

    preliminary_rrp = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Предварительная РРЦ",
    )

    minimum_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Минимальная цена",
    )

    calculated_rrp = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Расчетная РРЦ",
    )

    default_approved_rrp = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="РРЦ по умолчанию",
    )

    calculated_distr = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Расчетный distr",
    )

    calculated_distr_1 = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Расчетный distr_1",
    )

    calculated_small = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Расчетный малый опт",
    )

    calculated_medium = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Расчетный средний опт",
    )

    calculated_large = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Расчетный крупный опт",
    )

    margin_current = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Текущая маржа",
    )

    margin_calculated = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Расчетная маржа",
    )

    current_vs_calculated_percent = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Отклонение текущей цены",
    )

    calculation_status = models.CharField(
        max_length=20,
        default=STATUS_SUCCESS,
        db_index=True,
        verbose_name="Статус расчета",
    )

    warning_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Предупреждения",
    )

    error_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Ошибки",
    )

    calculation_details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Детали расчета",
    )

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iprice_snapshot_region"
        verbose_name = "iPrice snapshot region"
        verbose_name_plural = "iPrice snapshot regions"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "snapshot_product",
                    "sale_region",
                    "departure",
                ],
                name="iprice_snap_product_region_dep_uniq",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "snapshot_product",
                    "sale_region",
                ],
                name="iprice_sr_product_region_idx",
            ),
            models.Index(
                fields=[
                    "sale_region",
                    "departure",
                ],
                name="iprice_sr_region_departure_idx",
            ),
            models.Index(
                fields=[
                    "calculation_status",
                ],
                name="iprice_sr_status_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.snapshot_product.code_1c} | "
            f"{self.departure} -> {self.sale_region}"
        )


class IPriceSnapshotApproval(models.Model):
    snapshot_region = models.ForeignKey(
        IPriceSnapshotRegion,
        on_delete=models.CASCADE,
        related_name="approvals",
        verbose_name="Региональная строка",
    )

    revision = models.PositiveIntegerField(
        verbose_name="Версия утверждения",
    )

    approved_rrp = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        verbose_name="Утвержденная РРЦ",
    )

    approved_distr = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Утвержденный distr",
    )

    approved_distr_1 = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Утвержденный distr_1",
    )

    approved_small = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Утвержденный малый опт",
    )

    approved_medium = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Утвержденный средний опт",
    )

    approved_large = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Утвержденный крупный опт",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="iprice_approvals",
        verbose_name="Кем утверждено",
    )

    approved_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата утверждения",
    )

    comment = models.TextField(
        blank=True,
        default="",
        verbose_name="Комментарий",
    )

    is_current = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Текущее утверждение",
    )

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iprice_snapshot_approval"
        verbose_name = "iPrice snapshot approval"
        verbose_name_plural = "iPrice snapshot approvals"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "snapshot_region",
                    "revision",
                ],
                name="iprice_approval_region_revision_uniq",
            ),
            models.UniqueConstraint(
                fields=[
                    "snapshot_region",
                ],
                condition=Q(is_current=True),
                name="iprice_approval_current_region_uniq",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "snapshot_region",
                    "is_current",
                ],
                name="iprice_approval_current_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.snapshot_region} | "
            f"revision={self.revision} | "
            f"rrp={self.approved_rrp}"
        )


# ============================================================
# Analytics product directory and automatic analysis


class NomenclatureStock(models.Model):
    date = models.DateField(db_index=True)
    warehouse = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    nom_code = models.IntegerField(db_index=True)
    nomenclature = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    quantity = models.DecimalField(max_digits=24, decimal_places=6, blank=True, null=True)
    stock = models.DecimalField(max_digits=24, decimal_places=6, blank=True, null=True)
    dev_maximum = models.DecimalField(max_digits=24, decimal_places=6, blank=True, null=True)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nomenclature_stock"
        indexes = [
            models.Index(fields=["date", "nom_code"], name="nom_stock_date_code_idx"),
            models.Index(fields=["date", "warehouse"], name="nom_stock_date_wh_idx"),
        ]
