from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from dashboards.models import (
    Dashboard,
    DashboardAccess,
)


DASHBOARD_MENU_CONFIG = {
    "Общее": [
        (
            "Projects",
            "Проекты",
        ),
        (
            "Revenue",
            "Динамика выручки",
        ),
    ],

    "ECOM": [
        (
            "Wordstat",
            "Тренды и сезонность",
        ),
    ],

    "Закупки": [
        (
            "Purchases",
            "Сырье",
        ),
        (
            "Accreceiv",
            "ДЗ",
        ),
        (
            "Turnover",
            "Остатки",
        ),
    ],

    "Продажи": [
        (
            "PlannedSales",
            "План/Факт продаж",
        ),
        (
            "CRM Analytics",
            "Аналитика CRM",
        ),
    ],
}


class DashboardMenuView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        allowed_dashboard_ids = set(
            DashboardAccess.objects
            .filter(
                user=request.user,
                can_view=True,
            )
            .values_list(
                "dashboard_id",
                flat=True,
            )
        )

        # Для обычных dashboard сохраняем
        # существующую модель доступа.
        #
        # Superuser также должен видеть все
        # dashboard без обязательного создания
        # DashboardAccess.
        if request.user.is_superuser:
            dashboard_queryset = (
                Dashboard.objects.all()
            )
        else:
            dashboard_queryset = (
                Dashboard.objects.filter(
                    Q(id__in=allowed_dashboard_ids)
                    | Q(owner=request.user)
                )
            )

        dashboards = {
            dashboard.name: dashboard
            for dashboard in dashboard_queryset
        }

        sections = {}

        # ----------------------------------------------------
        # Обычные dashboard из базы данных
        # ----------------------------------------------------

        for (
            section_name,
            items,
        ) in DASHBOARD_MENU_CONFIG.items():
            section_items = []

            for (
                dashboard_name,
                display_name,
            ) in items:
                dashboard = dashboards.get(
                    dashboard_name
                )

                if dashboard is None:
                    continue

                section_items.append({
                    "id": dashboard.id,
                    "slug": dashboard.slug,
                    "name": display_name,
                    "url": (
                        f"/dashboards/"
                        f"{dashboard.slug}"
                    ),
                    "icon": "🗁",
                })

            if section_items:
                sections[
                    section_name
                ] = section_items

        # ----------------------------------------------------
        # iPrice использует обычную запись Dashboard,
        # но отображается прямой ссылкой верхнего уровня.
        # ----------------------------------------------------

        iprice_dashboard = dashboards.get("IPrice")

        if iprice_dashboard is not None:
            sections["iPrice"] = [{
                "id": iprice_dashboard.id,
                "slug": iprice_dashboard.slug,
                "name": "iPrice",
                "url": "/iprice",
                "icon": "🗁",
                "navigation_type": "section_link",
            }]

        return Response({
            "sections": sections,
        })
