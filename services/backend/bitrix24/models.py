from django.db import models


class BitrixSyncRun(models.Model):
    class Mode(models.TextChoices):
        FULL = "full", "Полная загрузка"
        INCREMENTAL = "incremental", "Инкрементальная загрузка"
        REPAIR = "repair", "Восстановление"

    class Status(models.TextChoices):
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успешно"
        FAILED = "failed", "Ошибка"

    entity = models.CharField(max_length=64, db_index=True)
    mode = models.CharField(max_length=16, choices=Mode.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
        db_index=True,
    )
    source_updated_from = models.DateTimeField(null=True, blank=True)
    source_updated_to = models.DateTimeField(null=True, blank=True)
    rows_received = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_updated = models.PositiveIntegerField(default=0)
    rows_deactivated = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_text = models.TextField(blank=True, default="")

    class Meta:
        db_table = "bitrix24_sync_run"
        ordering = ("-started_at", "-id")
        indexes = [
            models.Index(
                fields=("entity", "status", "started_at"),
                name="bitrix24_run_entity_status_idx",
            ),
        ]


class BitrixSyncState(models.Model):
    class Status(models.TextChoices):
        IDLE = "idle", "Ожидает"
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успешно"
        FAILED = "failed", "Ошибка"

    entity = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.IDLE,
    )
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_source_updated_at = models.DateTimeField(null=True, blank=True)
    last_source_id = models.BigIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    rows_received = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_updated = models.PositiveIntegerField(default=0)
    rows_deactivated = models.PositiveIntegerField(default=0)
    error_text = models.TextField(blank=True, default="")
    last_run = models.ForeignKey(
        BitrixSyncRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="states",
    )
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bitrix24_sync_state"


class BitrixRawBase(models.Model):
    source_created_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BitrixDepartment(BitrixRawBase):
    department_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255)
    parent_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    head_user_id = models.BigIntegerField(null=True, blank=True)
    sort = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "bitrix24_department"
        ordering = ("sort", "name", "department_id")

    def __str__(self):
        return self.name


class BitrixDealCategory(BitrixRawBase):
    category_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255)
    sort = models.IntegerField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "bitrix24_deal_category"


class BitrixDeal(BitrixRawBase):
    deal_id = models.BigIntegerField(unique=True)
    title = models.TextField(blank=True, default="")
    category_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    stage_id = models.CharField(max_length=128, blank=True, default="")
    stage_semantic_id = models.CharField(max_length=32, blank=True, default="")
    assigned_by_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    lead_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    company_id = models.BigIntegerField(null=True, blank=True)
    contact_id = models.BigIntegerField(null=True, blank=True)
    contact_ids = models.JSONField(default=list, blank=True)
    opportunity = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency_id = models.CharField(max_length=16, blank=True, default="")
    source_id = models.CharField(max_length=128, blank=True, default="")
    begin_date = models.DateTimeField(null=True, blank=True)
    close_date = models.DateTimeField(null=True, blank=True)
    closed = models.BooleanField(default=False)

    class Meta:
        db_table = "bitrix24_deal"


class BitrixUser(BitrixRawBase):
    user_id = models.BigIntegerField(unique=True)
    active = models.BooleanField(default=True, db_index=True)
    first_name = models.CharField(max_length=255, blank=True, default="")
    last_name = models.CharField(max_length=255, blank=True, default="")
    second_name = models.CharField(max_length=255, blank=True, default="")
    full_name = models.CharField(max_length=767, blank=True, default="")
    email = models.CharField(max_length=255, blank=True, default="")
    work_position = models.CharField(max_length=255, blank=True, default="")
    department_ids = models.JSONField(default=list, blank=True)
    primary_department_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "bitrix24_user"
        ordering = ("full_name", "user_id")

    def __str__(self):
        return self.full_name or str(self.user_id)


class BitrixUserDepartment(models.Model):
    user = models.ForeignKey(
        BitrixUser,
        on_delete=models.CASCADE,
        related_name="department_links",
    )
    department = models.ForeignKey(
        BitrixDepartment,
        on_delete=models.CASCADE,
        related_name="user_links",
    )
    position = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bitrix24_user_department"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "department"),
                name="bitrix24_user_department_uniq",
            ),
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(is_primary=True),
                name="bitrix24_user_primary_department_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("department", "is_primary"),
                name="bitrix24_user_dept_primary_idx",
            ),
        ]


class BitrixManagerTracking(models.Model):
    user_id = models.BigIntegerField(unique=True)
    manager_name = models.CharField(max_length=767)
    department_name = models.CharField(max_length=255)
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bitrix24_manager_tracking"
        ordering = ("manager_name", "user_id")

    def __str__(self):
        return self.manager_name


class BitrixCrmDictionary(BitrixRawBase):
    entity_id = models.CharField(max_length=64, db_index=True)
    status_id = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    sort = models.IntegerField(null=True, blank=True)
    semantics = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        db_table = "bitrix24_crm_dictionary"
        ordering = ("entity_id", "sort", "status_id")
        constraints = [
            models.UniqueConstraint(
                fields=("entity_id", "status_id"),
                name="bitrix24_crm_dictionary_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.entity_id}: {self.name}"


class BitrixCrmField(BitrixRawBase):
    entity_type_id = models.PositiveIntegerField(db_index=True)
    field_code = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True, default="")
    data_type = models.CharField(max_length=64, blank=True, default="")
    is_multiple = models.BooleanField(default=False)
    is_required = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False)

    class Meta:
        db_table = "bitrix24_crm_field"
        ordering = ("entity_type_id", "field_code")
        constraints = [
            models.UniqueConstraint(
                fields=("entity_type_id", "field_code"),
                name="bitrix24_crm_field_uniq",
            ),
        ]


class BitrixLead(BitrixRawBase):
    lead_id = models.BigIntegerField(unique=True)
    title = models.TextField(blank=True, default="")
    name = models.CharField(max_length=255, blank=True, default="")
    company_title = models.CharField(max_length=255, blank=True, default="")
    company_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    contact_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    source_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    status_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    status_semantic_id = models.CharField(max_length=32, blank=True, default="")
    assigned_by_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    created_by_id = models.BigIntegerField(null=True, blank=True)
    updated_by_id = models.BigIntegerField(null=True, blank=True)
    moved_by_id = models.BigIntegerField(null=True, blank=True)
    moved_time = models.DateTimeField(null=True, blank=True)
    closed_time = models.DateTimeField(null=True, blank=True)
    last_activity_time = models.DateTimeField(null=True, blank=True)
    opportunity = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency_id = models.CharField(max_length=16, blank=True, default="")
    is_return_customer = models.BooleanField(null=True, blank=True)
    project_id = models.CharField(max_length=128, blank=True, default="")
    activity_event_id = models.CharField(max_length=128, blank=True, default="")
    originator_id = models.CharField(max_length=255, blank=True, default="")
    address_city = models.CharField(max_length=255, blank=True, default="")
    address_province = models.CharField(max_length=255, blank=True, default="")
    address_country = models.CharField(max_length=255, blank=True, default="")
    utm_source = models.TextField(blank=True, default="")
    utm_medium = models.TextField(blank=True, default="")
    utm_campaign = models.TextField(blank=True, default="")
    utm_content = models.TextField(blank=True, default="")
    utm_term = models.TextField(blank=True, default="")

    class Meta:
        db_table = "bitrix24_lead"
        ordering = ("-source_created_at", "-lead_id")
        indexes = [
            models.Index(
                fields=("source_created_at", "source_id"),
                name="b24_lead_created_source_idx",
            ),
            models.Index(
                fields=("assigned_by_id", "status_id"),
                name="b24_lead_manager_status_idx",
            ),
        ]

    def __str__(self):
        return self.title or str(self.lead_id)


class BitrixStageHistory(models.Model):
    history_id = models.BigIntegerField()
    entity_type_id = models.PositiveIntegerField()
    entity_id = models.BigIntegerField()
    category_id = models.BigIntegerField(null=True, blank=True)
    stage_id = models.CharField(max_length=128, db_index=True)
    stage_semantic_id = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField()
    created_by_id = models.BigIntegerField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bitrix24_stage_history"
        ordering = ("entity_type_id", "entity_id", "created_at", "history_id")
        constraints = [
            models.UniqueConstraint(
                fields=("entity_type_id", "history_id"),
                name="bitrix24_stage_history_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("entity_type_id", "entity_id", "created_at"),
                name="bitrix24_stage_entity_time_idx",
            ),
        ]


class BitrixStageInterval(models.Model):
    entity_type_id = models.PositiveIntegerField()
    entity_id = models.BigIntegerField()
    history_id = models.BigIntegerField()
    sequence_number = models.PositiveIntegerField()
    stage_id = models.CharField(max_length=128, db_index=True)
    entered_at = models.DateTimeField()
    left_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.BigIntegerField(default=0)
    duration_days = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    is_current = models.BooleanField(default=False, db_index=True)
    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "bitrix24_stage_interval"
        ordering = ("entity_type_id", "entity_id", "sequence_number")
        constraints = [
            models.UniqueConstraint(
                fields=("entity_type_id", "history_id"),
                name="bitrix24_stage_interval_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(duration_seconds__gte=0),
                name="bitrix24_stage_duration_nonneg",
            ),
        ]
        indexes = [
            models.Index(
                fields=("entity_type_id", "entity_id", "entered_at"),
                name="b24_interval_entity_time_idx",
            ),
        ]


class BitrixLeadProcessing(models.Model):
    class ProcessingState(models.TextChoices):
        IN_PROGRESS = "in_progress", "Обработка продолжается"
        COMPLETED = "completed", "Обработан"
        NO_HISTORY = "no_history", "Нет истории стадий"
        INVALID_HISTORY = "invalid_history", "Некорректная история"

    lead_id = models.BigIntegerField(unique=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    first_stage_change_at = models.DateTimeField(null=True, blank=True)
    first_processing_at = models.DateTimeField(null=True, blank=True)
    processing_duration_seconds = models.BigIntegerField(null=True, blank=True)
    processing_duration_days = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
    )
    processing_state = models.CharField(
        max_length=32,
        choices=ProcessingState.choices,
        db_index=True,
    )
    current_status_id = models.CharField(max_length=128, blank=True, default="")
    current_status_since = models.DateTimeField(null=True, blank=True)
    current_status_duration_seconds = models.BigIntegerField(null=True, blank=True)
    current_status_duration_days = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
    )
    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "bitrix24_lead_processing"
        indexes = [
            models.Index(
                fields=("processing_state", "processing_duration_days"),
                name="b24_processing_state_days_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(processing_duration_seconds__isnull=True)
                    | models.Q(processing_duration_seconds__gte=0)
                ),
                name="bitrix24_processing_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(current_status_duration_seconds__isnull=True)
                    | models.Q(current_status_duration_seconds__gte=0)
                ),
                name="bitrix24_current_duration_nonneg",
            ),
        ]


class BitrixLeadAnalytics(models.Model):
    lead_id = models.BigIntegerField(unique=True)
    title = models.TextField(blank=True, default="")
    source_created_at = models.DateTimeField(null=True, blank=True, db_index=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    opportunity = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    source_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    source_name = models.CharField(max_length=255, blank=True, default="")
    status_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    status_name = models.CharField(max_length=255, blank=True, default="")
    status_semantic_id = models.CharField(max_length=32, blank=True, default="")
    dashboard_status = models.CharField(max_length=32, db_index=True)
    manager_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    manager_name = models.CharField(max_length=767, blank=True, default="")
    primary_department_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    department_name = models.CharField(max_length=255, blank=True, default="")
    company_name = models.TextField(blank=True, default="")
    is_return_customer = models.BooleanField(null=True, blank=True)
    project_id = models.CharField(max_length=128, blank=True, default="")
    project_name = models.TextField(blank=True, default="")
    activity_name = models.TextField(blank=True, default="")
    last_activity_time = models.DateTimeField(null=True, blank=True)
    is_apm = models.BooleanField(default=False, db_index=True)
    is_low_quality = models.BooleanField(default=False, db_index=True)
    is_unmapped = models.BooleanField(default=False, db_index=True)
    is_processed = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)
    first_processing_at = models.DateTimeField(null=True, blank=True)
    processing_duration_seconds = models.BigIntegerField(null=True, blank=True)
    processing_duration_days = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
    )
    processing_state = models.CharField(max_length=32, blank=True, default="")
    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "bitrix24_lead_analytics"
        indexes = [
            models.Index(
                fields=("source_created_at", "primary_department_id"),
                name="b24_analytics_date_dept_idx",
            ),
            models.Index(
                fields=("source_created_at", "source_id"),
                name="b24_analytics_date_source_idx",
            ),
            models.Index(
                fields=("source_created_at", "dashboard_status"),
                name="b24_analytics_date_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~(models.Q(is_apm=True) & models.Q(is_low_quality=True)),
                name="bitrix24_analytics_apm_not_lowq",
            ),
        ]
