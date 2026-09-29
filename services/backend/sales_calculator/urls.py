from django.urls import path
from .api import SettingsView, ProductsView, CalculationView, RefreshView, ExportView

urlpatterns = [
    path("settings/", SettingsView.as_view()), path("products/", ProductsView.as_view()),
    path("calculate/", CalculationView.as_view()), path("refresh/", RefreshView.as_view()),
    path("export/", ExportView.as_view()),
]
