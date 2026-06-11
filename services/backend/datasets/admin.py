from django.contrib import admin

from .models import Dataset
from .models import DatasetRow
from .models import FbProject

admin.site.register(Dataset)
admin.site.register(DatasetRow)

admin.site.register(FbProject)