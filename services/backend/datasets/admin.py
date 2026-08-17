from django.contrib import admin

from .models import (
    Dataset,
    DatasetRow,
)

admin.site.register(Dataset)
admin.site.register(DatasetRow)
