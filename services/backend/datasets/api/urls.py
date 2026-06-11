from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DatasetViewSet
from .views import DatasetRowViewSet


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
    path("", include(router.urls)),
]