from django.contrib import admin


from .models import (
    Dataset,
    DatasetRow,
    FbProject,
    YdWordstatFor,
    FBPurchasesUse,
    FBPurchasesUseIndicator,
    TurnoverClear,
    TurnoverIndicator,
)




admin.site.register(Dataset)
admin.site.register(DatasetRow)

admin.site.register(FbProject)
admin.site.register(YdWordstatFor)

admin.site.register(FBPurchasesUse)
admin.site.register(FBPurchasesUseIndicator)

admin.site.register(TurnoverClear)
admin.site.register(TurnoverIndicator)