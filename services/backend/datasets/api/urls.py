from django.urls import include
from django.urls import path

from rest_framework.routers import DefaultRouter

from .views import DatasetViewSet
from .views import DatasetRowViewSet



router = DefaultRouter()

router.register(
    r"datasets",
    DatasetViewSet,
    basename="datasets"
)

router.register(
    r"rows",
    DatasetRowViewSet,
    basename="rows"
)

urlpatterns = [
    path("", include(router.urls)),
]