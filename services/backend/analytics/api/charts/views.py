from rest_framework.views import APIView
from rest_framework.response import Response

from analytics.services.charts.bar import build_bar_chart
from analytics.services.charts.line import build_line_chart
from analytics.services.charts.pie import build_pie_chart

from analytics.cache.charts_cache import chart_cache_key

from django.core.cache import cache



class ChartView(APIView):

    def get(self, request, dataset_id):

        chart_type = request.query_params.get("type")
        x = request.query_params.get("x")
        y = request.query_params.get("y")

        params = {
            "x": x,
            "y": y,
        }

        cache_key = chart_cache_key(
            dataset_id,
            chart_type,
            params
        )

        cached = cache.get(cache_key)

        if cached:
            return Response(cached)

        if chart_type == "bar":
            result = build_bar_chart(dataset_id, x, y)

        elif chart_type == "line":
            result = build_line_chart(dataset_id, x, y)

        elif chart_type == "pie":
            result = build_pie_chart(dataset_id, x)

        else:
            return Response(
                {"error": "unknown chart type"},
                status=400
            )

        cache.set(cache_key, result, 300)

        return Response(result)