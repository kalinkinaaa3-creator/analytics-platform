from django.urls import include, path
from rest_framework.routers import DefaultRouter



from .views import (
    DatasetViewSet,
    DatasetRowViewSet,
    FbProjectUploadView,
    YdWordstatUploadView,
    FBPurchasesUploadView,
    FBTurnoverUploadView,
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

    path("", include(router.urls)),
]