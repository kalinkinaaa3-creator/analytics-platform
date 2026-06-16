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