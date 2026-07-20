from django.db import models


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

    month_1 = models.IntegerField(blank=True, null=True)
    month_2 = models.IntegerField(blank=True, null=True)
    month_3 = models.IntegerField(blank=True, null=True)
    month_4 = models.IntegerField(blank=True, null=True)
    month_5 = models.IntegerField(blank=True, null=True)
    month_6 = models.IntegerField(blank=True, null=True)
    month_7 = models.IntegerField(blank=True, null=True)
    month_8 = models.IntegerField(blank=True, null=True)
    month_9 = models.IntegerField(blank=True, null=True)
    month_10 = models.IntegerField(blank=True, null=True)
    month_11 = models.IntegerField(blank=True, null=True)
    month_12 = models.IntegerField(blank=True, null=True)

    total = models.IntegerField(blank=True, null=True)

    average = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
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

    desktop = models.IntegerField(blank=True, null=True)
    phone = models.IntegerField(blank=True, null=True)
    tablet = models.IntegerField(blank=True, null=True)
    other_device = models.IntegerField(blank=True, null=True)

    ekb_macroregion = models.IntegerField(blank=True, null=True)
    kras_macroregion = models.IntegerField(blank=True, null=True)
    mos_macroregion = models.IntegerField(blank=True, null=True)
    nign_macroregion = models.IntegerField(blank=True, null=True)
    novos_macroregion = models.IntegerField(blank=True, null=True)
    spb_macroregion = models.IntegerField(blank=True, null=True)
    sng_macroregion = models.IntegerField(blank=True, null=True)
    other_macroregion = models.IntegerField(blank=True, null=True)

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
    cost = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
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
        return f"{self.source}: {self.prefix}"


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
        (STATUS_ACTIVE, "Активен"),
        (STATUS_INACTIVE, "Неактивен"),
    )

    product_key_base = models.BigIntegerField(db_index=True)
    product_key_competitor = models.BigIntegerField(db_index=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )

    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "parser_product_match"
        verbose_name = "Parser: product matching"
        verbose_name_plural = "Parser: product matches"
        unique_together = ("product_key_base", "product_key_competitor")
        indexes = [
            models.Index(fields=["product_key_base", "product_key_competitor"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.product_key_base} → {self.product_key_competitor}"




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
        (STATUS_ACTIVE, "Активен"),
        (STATUS_INACTIVE, "Неактивен"),
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
        verbose_name = "Parser: product classification"
        verbose_name_plural = "Parser: products classification"

    def __str__(self):
        return f"{self.product_key}"








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


class YdWordstatRegionRef(models.Model):
    country_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    macroregion_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    region_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    region_value = models.IntegerField(unique=True, db_index=True)
    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_ref_region"
        verbose_name = "YD Wordstat region ref"
        verbose_name_plural = "YD Wordstat region refs"
        indexes = [
            models.Index(fields=["country_label", "macroregion_label"]),
            models.Index(fields=["region_label", "region_value"]),
        ]

    def __str__(self):
        return f"{self.region_label} ({self.region_value})"


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
    count = models.IntegerField(blank=True, null=True)

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
    count = models.IntegerField(blank=True, null=True)

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


class YdWordstatRegionRaw(models.Model):
    phrase = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    region_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    region_value = models.IntegerField(blank=True, null=True, db_index=True)

    date = models.DateField(blank=True, null=True, db_index=True)
    count = models.IntegerField(blank=True, null=True)

    feature = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    category = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    country_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    macroregion_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    macroregion_iplast = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_region"
        verbose_name = "YD Wordstat region raw"
        verbose_name_plural = "YD Wordstat region raw"
        indexes = [
            models.Index(fields=["phrase", "region_value", "date"]),
            models.Index(fields=["region_value", "date"]),
            models.Index(fields=["macroregion_iplast", "date"]),
            models.Index(fields=["feature", "category", "phrase"]),
            models.Index(fields=["country_label", "macroregion_label"]),
        ]

    def __str__(self):
        return f"{self.phrase} {self.region_value} {self.date}: {self.count}"


class YdWordstatMacroregionRaw(models.Model):
    phrase = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    date = models.DateField(blank=True, null=True, db_index=True)
    count = models.IntegerField(blank=True, null=True)

    feature = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    category = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    country_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    macroregion_label = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    date_add = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "yd_wordstat_macroregion_label"
        verbose_name = "YD Wordstat macroregion raw"
        verbose_name_plural = "YD Wordstat macroregion raw"
        indexes = [
            models.Index(fields=["phrase", "date"]),
            models.Index(fields=["macroregion_label", "date"]),
            models.Index(fields=["feature", "category", "phrase"]),
        ]

    def __str__(self):
        return f"{self.phrase} {self.macroregion_label} {self.date}: {self.count}"






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