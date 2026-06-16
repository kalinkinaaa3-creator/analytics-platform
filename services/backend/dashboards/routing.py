from django.urls import path

from dashboards.consumers import DashboardConsumer


websocket_urlpatterns = [
    path("ws/dashboards/", DashboardConsumer.as_asgi()),
]