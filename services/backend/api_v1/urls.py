from django.urls import path, include
from .views import health



urlpatterns = [
    path("health/", health),
]