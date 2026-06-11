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