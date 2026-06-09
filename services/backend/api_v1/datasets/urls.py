from django.urls import path
from .views import list_datasets

urlpatterns = [
    path("", list_datasets),
]