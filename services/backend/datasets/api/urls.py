from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .tara_views import TaraStatusView, TaraSessionUploadView, TaraCancelView, TaraInternalRunView



from .views import (
    DatasetViewSet,
    DatasetRowViewSet,

    FbProjectUploadView,
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
    PurchasesPlanView,
    TurnoverPlanView,
    PublicPurchasesPlanView,
    PublicTurnoverPlanView,


    ParserPrefixUploadView,
    ProductClassificationUploadView,

    YdWordstatPhraseRefUploadView,
    YdWordstatDeviceRefUploadView,
    YdWordstatIplastRegionRefUploadView,

    YdWordstatAllLoadFromApiView,
    YdWordstatDeviceLoadFromApiView,
    YdWordstatRegionLoadFromApiView,
    YdWordstatFullLoadFromApiView,

    RevenueExportView,
    SalesRefreshView,

    NomenclatureApiLoadView,
    NomenclaturePriceApiLoadView,

    TransportCostUploadView,
    ProductCostUploadView,
    IPriceProductCostTemplateExportView,
    IPriceAccessView,
    IPriceUploadTemplateExportView,
    IPriceParserProductsExportView,
    IPricePreparationCheckExportView,
    IPriceCalculationConfigUploadView,
    ParserMasterPipelineRunView,

    IPriceSnapshotRunView,
    IPriceParameterChangeView,
    IPriceSnapshotListView,
    IPriceSnapshotDetailView,
    IPriceSnapshotActivateView,
    IPriceSnapshotRowsView,
    IPriceSnapshotFiltersView,
    IPriceSnapshotProductDetailView,
    IPriceSnapshotApprovalSaveView,
    IPriceSnapshotApprovalHistoryView,
    IPriceSnapshotExportView,
    IPriceSnapshotMarketAssortmentView,
    IPriceSnapshotCompetitorSelectionView,
    IPriceSnapshotOwnAssortmentView,
    IPriceSnapshotCompareView,
    IPriceSnapshotCompareFiltersView,
    IPriceHealthView,
    IPricePriceAnalyticsView,
    IPricePriceZoneConfigView,
    IPriceAnalyticsSelectionView,
    IPriceAnalyticsSelectionDetailView,

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
    path('parsers/tara/status/', TaraStatusView.as_view()),
    path('parsers/tara/<int:run_id>/session/', TaraSessionUploadView.as_view()),
    path('parsers/tara/<int:run_id>/cancel/', TaraCancelView.as_view()),
    path('parsers/tara/internal/run/', TaraInternalRunView.as_view()),
    path(
        "fb-project/upload/",
        FbProjectUploadView.as_view(),
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
    path("fb-purchases/plans/", PurchasesPlanView.as_view()),
    path("fb-turnover/plans/", TurnoverPlanView.as_view()),
    path("fb-accreceiv/export/", FBAccreceivExportView.as_view()),

    path("revenue/export/", RevenueExportView.as_view()),

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
    path("public-group/<uuid:token>/fb-purchases/plans/", PublicPurchasesPlanView.as_view()),
    path("public-group/<uuid:token>/fb-turnover/plans/", PublicTurnoverPlanView.as_view()),



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

    path(
        "parsers/master/run/",
        ParserMasterPipelineRunView.as_view(),
    ),

    path(
        "parsers/product-classification/upload/",
        ProductClassificationUploadView.as_view(),
    ),

    path(
        "yd-wordstat/phrase-ref-upload/",
        YdWordstatPhraseRefUploadView.as_view(),
    ),
    path(
        "yd-wordstat/device-ref-upload/",
        YdWordstatDeviceRefUploadView.as_view(),
    ),
    path(
        "yd-wordstat/iplast-region-ref-upload/",
        YdWordstatIplastRegionRefUploadView.as_view(),
    ),



    path(
        "yd-wordstat/all/load-from-api/",
        YdWordstatAllLoadFromApiView.as_view(),
    ),
    path(
        "yd-wordstat/device/load-from-api/",
        YdWordstatDeviceLoadFromApiView.as_view(),
    ),
    path(
        "yd-wordstat/region/load-from-api/",
        YdWordstatRegionLoadFromApiView.as_view(),
    ),
    path(
        "yd-wordstat/load-from-api/",
        YdWordstatFullLoadFromApiView.as_view(),
    ),
    path("sales/refresh/", SalesRefreshView.as_view()),


    path("nomenclature/load-from-api/", NomenclatureApiLoadView.as_view()),

    path(
        "nomenclature-price/load-from-api/",
        NomenclaturePriceApiLoadView.as_view(),
    ),

    path(
        "iprice/access/",
        IPriceAccessView.as_view(),
    ),
    path(
        "iprice/transport-cost/upload/",
        TransportCostUploadView.as_view(),
    ),

    path(
        "iprice/product-cost/upload/",
        ProductCostUploadView.as_view(),
    ),
    path(
        "iprice/product-cost-template/export/",
        IPriceProductCostTemplateExportView.as_view(),
    ),
    path(
        "iprice/upload-templates/<str:upload_type>/export/",
        IPriceUploadTemplateExportView.as_view(),
    ),
    path(
        "iprice/parser-products/export/",
        IPriceParserProductsExportView.as_view(),
    ),
    path(
        "iprice/preparation-check/export/",
        IPricePreparationCheckExportView.as_view(),
    ),

    path(
        "iprice/data/health/",
        IPriceHealthView.as_view(),
    ),

    path(
        "iprice/calculation-config/upload/",
        IPriceCalculationConfigUploadView.as_view(),
    ),

    path(
        "iprice/snapshots/run/",
        IPriceSnapshotRunView.as_view(),
    ),
    path(
        "iprice/snapshots/<int:snapshot_id>/parameters/",
        IPriceParameterChangeView.as_view(),
    ),

    path(
        "iprice/analytics/price-zones/",
        IPricePriceZoneConfigView.as_view(),
    ),
    path(
        "iprice/snapshots/<int:snapshot_id>/analytics/selection/",
        IPriceAnalyticsSelectionView.as_view(),
    ),
    path(
        "iprice/analytics/selection/<str:token>/",
        IPriceAnalyticsSelectionDetailView.as_view(),
    ),

    path(
        "iprice/snapshots/",
        IPriceSnapshotListView.as_view(),
    ),

    path(
        "iprice/snapshots/compare/",
        IPriceSnapshotCompareView.as_view(),
    ),

    path(
        "iprice/snapshots/compare/filters/",
        (
            IPriceSnapshotCompareFiltersView
            .as_view()
        ),
    ),

    path(
        "iprice/snapshots/<int:snapshot_id>/",
        IPriceSnapshotDetailView.as_view(),
    ),

    path(
        "iprice/snapshots/<int:snapshot_id>/activate/",
        IPriceSnapshotActivateView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/rows/"
        ),
        IPriceSnapshotRowsView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/filters/"
        ),
        IPriceSnapshotFiltersView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/analytics/"
        ),
        IPricePriceAnalyticsView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/export/"
        ),
        IPriceSnapshotExportView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/products/"
            "<int:product_id>/"
        ),
        IPriceSnapshotProductDetailView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/products/"
            "<int:product_id>/"
            "market-assortment/"
        ),
        (
            IPriceSnapshotMarketAssortmentView
            .as_view()
        ),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/products/"
            "<int:product_id>/"
            "competitor-selection/"
        ),
        IPriceSnapshotCompetitorSelectionView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/products/"
            "<int:product_id>/"
            "own-assortment/"
        ),
        IPriceSnapshotOwnAssortmentView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/regions/"
            "<int:region_id>/approval/"
        ),
        IPriceSnapshotApprovalSaveView.as_view(),
    ),

    path(
        (
            "iprice/snapshots/"
            "<int:snapshot_id>/regions/"
            "<int:region_id>/approval-history/"
        ),
        IPriceSnapshotApprovalHistoryView.as_view(),
    ),




    path("", include(router.urls)),
]
