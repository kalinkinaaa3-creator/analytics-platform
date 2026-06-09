from django.contrib import admin

from .models import Dataset
from .models import DatasetRow


admin.site.register(Dataset)
admin.site.register(DatasetRow)