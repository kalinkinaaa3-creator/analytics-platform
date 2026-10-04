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
            "projects",
        ),
        (
            "Revenue",
            "Динамика выручки",
            "revenue",
        ),
    ],

    "ECOM": [
        (
            "Wordstat",
            "Тренды и сезонность",
            "trends",
        ),
        (
            "SEO-аналитика",
            "SEO-аналитика",
            "search",
        ),
        (
            "Контекстная реклама",
            "Контекстная реклама",
            "advertising",
        ),
        (
            "Лидогенерация",
            "Лидогенерация",
            "leads",
        ),
    ],

    "Закупки": [
        (
            "Purchases",
            "Сырье",
            "purchases",
        ),
        (
            "Accreceiv",
            "ДЗ",
            "receivables",
        ),
        (
            "Turnover",
            "Остатки",
            "stock",
        ),
    ],

    "Продажи": [
        ("Commercial Price", "Коммерческий прайс", "ruble"),
        (
            "PlannedSales",
            "План/Факт продаж",
            "sales",
        ),
        (
            "CRM Analytics",
            "Аналитика CRM",
            "crm",
        ),
    ],
}


class DashboardMenuView(APIView):
    organization_aware = True
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

        dashboard_list = list(dashboard_queryset.filter(organization=request.organization, show_in_menu=True).order_by("menu_order", "id"))
        dashboards = {dashboard.name: dashboard for dashboard in dashboard_list}

        sections = {}

        # ----------------------------------------------------
        # Обычные dashboard из базы данных
        # ----------------------------------------------------

        for (
            section_name,
            items,
        ) in (DASHBOARD_MENU_CONFIG.items() if request.organization.code == "iplast" else []):
            for (
                dashboard_name,
                display_name,
                icon,
            ) in items:
                dashboard = dashboards.get(
                    dashboard_name
                )

                if dashboard is None:
                    continue

                sections.setdefault(dashboard.menu_group or section_name, []).append({
                    "id": dashboard.id,
                    "slug": dashboard.slug,
                    "name": dashboard.display_name or display_name,
                    "url": (
                        f"/dashboards/"
                        f"{dashboard.slug}"
                    ),
                    "icon": dashboard.menu_icon or icon,
                })

        # ----------------------------------------------------
        # iPrice использует обычную запись Dashboard,
        # но отображается прямой ссылкой верхнего уровня.
        # ----------------------------------------------------

        iprice_dashboard = dashboards.get("IPrice") if request.organization.code == "iplast" else None

        if iprice_dashboard is not None:
            sections.setdefault(iprice_dashboard.menu_group or "iPrice", []).append({
                "id": iprice_dashboard.id,
                "slug": iprice_dashboard.slug,
                "name": iprice_dashboard.display_name or "iPrice",
                "url": "/iprice",
                "icon": "🗁",
                "navigation_type": "section_link",
            })

        configured_ids = {item["id"] for items in sections.values() for item in items}
        for dashboard in dashboard_list:
            if dashboard.id in configured_ids or not dashboard.menu_group:
                continue
            sections.setdefault(dashboard.menu_group, []).append({
                "id": dashboard.id, "slug": dashboard.slug,
                "name": dashboard.display_name or dashboard.name,
                "url": f"/dashboards/{dashboard.slug}",
                "icon": dashboard.menu_icon or dashboard.component,
                "component": dashboard.component,
            })

        order = {dashboard.id: dashboard.menu_order for dashboard in dashboard_list}
        for items in sections.values():
            items.sort(key=lambda item: order[item["id"]])
        return Response({
            "sections": sections,
        })
