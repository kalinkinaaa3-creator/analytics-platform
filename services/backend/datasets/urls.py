from django.urls import path

from .views import DatasetUploadView


urlpatterns = [
    path(
        "upload/",
        DatasetUploadView.as_view(),
        name="dataset-upload",
    ),
]