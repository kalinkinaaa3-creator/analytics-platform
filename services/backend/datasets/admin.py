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
    AccreceivUse,
    AccreceivIndicator,
    PlannedSales,
    PlanSales,
    PlannedSalesDirectory,
)




admin.site.register(Dataset)
admin.site.register(DatasetRow)

admin.site.register(FbProject)
admin.site.register(YdWordstatFor)

admin.site.register(FBPurchasesUse)
admin.site.register(FBPurchasesUseIndicator)

admin.site.register(TurnoverClear)
admin.site.register(TurnoverIndicator)

admin.site.register(AccreceivUse)
admin.site.register(AccreceivIndicator)


admin.site.register(PlannedSales)
admin.site.register(PlanSales)
admin.site.register(PlannedSalesDirectory)