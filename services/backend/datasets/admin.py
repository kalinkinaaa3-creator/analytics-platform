from django.contrib import admin

from .models import Dataset
from .models import DatasetRow
from .models import FbProject
from .models import YdWordstatFor

admin.site.register(Dataset)
admin.site.register(DatasetRow)

admin.site.register(FbProject)
admin.site.register(YdWordstatFor)