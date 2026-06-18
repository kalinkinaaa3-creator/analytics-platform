from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from dashboards.models import Dashboard, DashboardAccess


DASHBOARD_MENU_CONFIG = {
    "Общее": [
        ("Projects", "Проекты"),
    ],
    "ECOM": [
        ("Wordstat", "Тренды и сезонность"),
    ],
    "Закупки": [
        ("Purchases", "Сырье"),
        ("Accreceiv", "ДЗ"),
        ("Turnover", "Остатки"),
    ],
    "Продажи": [
        ("PlannedSales", "План/Факт продаж"),
    ],
}


class DashboardMenuView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        allowed_dashboard_ids = set(
            DashboardAccess.objects.filter(
                user=request.user,
                can_view=True,
            ).values_list("dashboard_id", flat=True)
        )

        dashboards = {
            dashboard.name: dashboard
            for dashboard in Dashboard.objects.filter(
                id__in=allowed_dashboard_ids
            )
        }

        sections = {}

        for section_name, items in DASHBOARD_MENU_CONFIG.items():
            section_items = []

            for dashboard_name, display_name in items:
                dashboard = dashboards.get(dashboard_name)

                if dashboard is None:
                    continue

                section_items.append({
                    "id": dashboard.id,
                    "slug": dashboard.slug,
                    "name": display_name,
                    "url": f"/dashboards/{dashboard.slug}",
                    "icon": "🗁",
                })

            if section_items:
                sections[section_name] = section_items

        return Response({
            "sections": sections,
        })