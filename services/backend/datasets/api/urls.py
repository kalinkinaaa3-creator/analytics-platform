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

    path("planned-sales/upload/", PlannedSalesUploadView.as_view()),
    path("planned-sales/plan-upload/", PlanSalesUploadView.as_view()),
    path("planned-sales/directory-upload/", PlannedSalesDirectoryUploadView.as_view()),
    
    path("planned-sales/save-plan/", PlannedSalesSavePlanView.as_view()),


    path("", include(router.urls)),
]