from django.urls import include, path
from rest_framework.routers import DefaultRouter



from .views import (
    DatasetViewSet,
    DatasetRowViewSet,

    FbProjectUploadView,
    YdWordstatUploadView,
    FBPurchasesUploadView,
    FBTurnoverUploadView,
    FBAccreceivUploadView,
    FBAccreceivIndicatorUploadView,
    FBPurchasesIndicatorUploadView,
    FBTurnoverIndicatorUploadView,

    WordstatExportView,
    FBPurchasesExportView,
    FBTurnoverExportView,
    FBAccreceivExportView,

    PlannedSalesUploadView,
    PlanSalesUploadView,
    PlannedSalesDirectoryUploadView,
    PlannedSalesSavePlanView,

    FbProjectApiLoadView,
    PlannedSalesApiLoadView,
    FBPurchasesApiLoadView,
    FBTurnoverApiLoadView,
    FBAccreceivApiLoadView,
    TableHealthCheckView,
    ProcessKillView,
    PublicFBTurnoverExportView, 
    PublicFBAccreceivExportView,
    PublicFBPurchasesExportView,


    ParserPrefixUploadView,

)


router = DefaultRouter()

router.register(
    r"",
    DatasetViewSet,
    basename="datasets"
)

router.register(
    r"rows",
    DatasetRowViewSet,
    basename="rows"
)



urlpatterns = [
    path(
        "fb-project/upload/",
        FbProjectUploadView.as_view(),
    ),

    path(
        "yd-wordstat/upload/",
        YdWordstatUploadView.as_view(),
    ),

    path(
        "fb-purchases/upload/",
        FBPurchasesUploadView.as_view(),
    ),

    path(
        "fb-turnover/upload/",
        FBTurnoverUploadView.as_view(),
    ),

    path(
        "fb-accreceiv/upload/",
        FBAccreceivUploadView.as_view(),
    ),
    
    path(
        "fb-accreceiv/indicator-upload/",
        FBAccreceivIndicatorUploadView.as_view(),
    ),

    path(
        "fb-purchases/indicator-upload/",
        FBPurchasesIndicatorUploadView.as_view(),
    ),

    path(
        "fb-turnover/indicator-upload/",
        FBTurnoverIndicatorUploadView.as_view(),
    ),


    path("yd-wordstat/export/", WordstatExportView.as_view()),
    path("fb-purchases/export/", FBPurchasesExportView.as_view()),
    path("fb-turnover/export/", FBTurnoverExportView.as_view()),
    path("fb-accreceiv/export/", FBAccreceivExportView.as_view()),

    path(
        "public-group/<uuid:token>/fb-turnover/export/",
        PublicFBTurnoverExportView.as_view(),
    ),
    path(
        "public-group/<uuid:token>/fb-accreceiv/export/",
        PublicFBAccreceivExportView.as_view(),
    ),
    path(
        "public-group/<uuid:token>/fb-purchases/export/",
        PublicFBPurchasesExportView.as_view(),
    ),



    path("planned-sales/upload/", PlannedSalesUploadView.as_view()),
    path("planned-sales/plan-upload/", PlanSalesUploadView.as_view()),
    path("planned-sales/directory-upload/", PlannedSalesDirectoryUploadView.as_view()),
    
    path("planned-sales/save-plan/", PlannedSalesSavePlanView.as_view()),


    path("fb-project/load-from-api/", FbProjectApiLoadView.as_view()),
    path("planned-sales/load-from-api/", PlannedSalesApiLoadView.as_view()),
    path("fb-purchases/load-from-api/", FBPurchasesApiLoadView.as_view()),
    path("fb-turnover/load-from-api/", FBTurnoverApiLoadView.as_view()),
    path("fb-accreceiv/load-from-api/", FBAccreceivApiLoadView.as_view()),

    path("maintenance/table-health/", TableHealthCheckView.as_view()),
    path("maintenance/process-kill/", ProcessKillView.as_view()),

    path(
        "parsers/prefixes/upload/",
        ParserPrefixUploadView.as_view(),
    ),


    path("", include(router.urls)),
]