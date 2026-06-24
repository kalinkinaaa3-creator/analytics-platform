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
    DashSales,
    FBPurchasesRaw,
    TurnoverRaw,
    AccreceivRaw,


    ParserPrefix,
    ParserProductUrl,
    ParserProductProperty,
    TaraProductPrice,
    PsProductPrice,
    TtProductPrice,

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

admin.site.register(DashSales)
admin.site.register(FBPurchasesRaw)
admin.site.register(TurnoverRaw)
admin.site.register(AccreceivRaw)



admin.site.register(ParserPrefix)
admin.site.register(ParserProductUrl)
admin.site.register(ParserProductProperty)

admin.site.register(TaraProductPrice)
admin.site.register(PsProductPrice)
admin.site.register(TtProductPrice)