from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),

    # API V1 - ЧЁТКАЯ СЕГМЕНТАЦИЯ
    path("api/v1/datasets/", include("datasets.api.urls")),
    path("api/v1/analytics/", include("analytics.api.urls")),
    path("api/v1/charts/", include("analytics.api.charts.urls")),
    path("api/v1/dashboards/", include("dashboards.api.urls")),
]

urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT,
)