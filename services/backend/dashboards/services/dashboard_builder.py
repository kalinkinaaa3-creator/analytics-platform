from dashboards.models import (
    Dashboard
)

from analytics.services.charts.bar import (
    build_bar_chart
)

from analytics.services.charts.line import (
    build_line_chart
)

from analytics.services.charts.pie import (
    build_pie_chart
)

from django.core.cache import cache

from dashboards.cache.dashboard_cache import (
    dashboard_cache_key
)


def build_dashboard(dashboard_id: int):

    key = dashboard_cache_key(dashboard_id)

    cached = cache.get(key)
    if cached:
        return cached

    dashboard = Dashboard.objects.prefetch_related(
        "widgets"
    ).get(id=dashboard_id)

    widgets_data = []

    for widget in dashboard.widgets.all():

        chart = None

        if widget.chart_type == "bar":
            chart = build_bar_chart(
                dataset_id=widget.dataset_id,
                x_field=widget.x_field,
                y_field=widget.y_field
            )

        elif widget.chart_type == "line":
            chart = build_line_chart(
                dataset_id=widget.dataset_id,
                x_field=widget.x_field,
                y_field=widget.y_field
            )

        elif widget.chart_type == "pie":
            chart = build_pie_chart(
                dataset_id=widget.dataset_id,
                field=widget.x_field
            )

        widgets_data.append({
            "id": widget.id,
            "title": widget.title,
            "chart_type": widget.chart_type,
            "position_x": widget.position_x,
            "position_y": widget.position_y,
            "width": widget.width,
            "height": widget.height,
            "chart": chart,
        })

    result = {
        "dashboard": {
            "id": dashboard.id,
            "name": dashboard.name,
            "description": dashboard.description,
        },
        "widgets": widgets_data,
    }

    cache.set(key, result, timeout=300)

    return result