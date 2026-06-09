from django.urls import path
from .views import list_reports

urlpatterns = [
    path("", list_reports),
]