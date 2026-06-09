from django.urls import path

from .views import ChartView


urlpatterns = [
    path(
        "datasets/<int:dataset_id>/chart/",
        ChartView.as_view(),
    ),
]