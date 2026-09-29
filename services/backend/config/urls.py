from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from dashboards.api.auth_views import LoggingTokenObtainPairView
from config.health import health


urlpatterns = [
    path("api/health/", health),
    path("admin/", admin.site.urls),

    path("api/token/", LoggingTokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),

    # API V1 - ЧЁТКАЯ СЕГМЕНТАЦИЯ
    path("api/v1/datasets/", include("datasets.api.urls")),

    path("api/v1/bitrix24/", include("bitrix24.api.urls")),
    path("api/v1/seo/", include("seo_analytics.api.urls")),
    path("api/v1/context/", include("context_analytics.api.urls")),
    path("api/v1/lead-generation/", include("lead_generation.api.urls")),
    path("api/v1/sales-calculator/", include("sales_calculator.urls")),
    
    path("api/v1/dashboards/", include("dashboards.api.urls")),
]

urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT,
)
