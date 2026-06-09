from django.urls import path

from .views import DatasetStatsView

urlpatterns = [
    path(
        "datasets/<int:dataset_id>/stats/",
        DatasetStatsView.as_view(),
    ),
]