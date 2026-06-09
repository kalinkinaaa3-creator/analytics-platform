from django.urls import path
from .views import list_dashboards

urlpatterns = [
    path("", list_dashboards),
]