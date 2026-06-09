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