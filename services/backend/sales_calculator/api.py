import json
import logging

from django.core.serializers.json import DjangoJSONEncoder
from django.http import FileResponse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboards.models import Dashboard
from dashboards.services.access import user_can_view_dashboard
from .configuration import DEFAULTS, CHARACTERISTICS, LOGISTICS, WAREHOUSES, FULL_COLUMNS, SIMPLE_COLUMNS, validate_config
from .models import SalesCalculatorPreference
from .warehouse import read_products
from .calculation import calculate
from .refresh import state_payload, request_refresh


def serializable(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


class AccessView(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.dashboard = Dashboard.objects.filter(organization__code="iplast", slug="commercial-price").first()
        if not self.dashboard or not user_can_view_dashboard(request.user, self.dashboard):
            raise PermissionDenied("Нет доступа к коммерческому прайсу")

    def config(self):
        preference = SalesCalculatorPreference.objects.filter(user=self.request.user).first()
        return validate_config(preference.config if preference else {})


class SettingsView(AccessView):
    def get(self, request):
        from datasets.models import NomenclatureStock
        config = self.config()
        warehouses = set(NomenclatureStock.objects.exclude(warehouse__isnull=True).exclude(warehouse="").values_list("warehouse", flat=True).distinct())
        warehouses.update(WAREHOUSES)
        warehouses.update(config["warehouses"])
        return Response({"config": config, "characteristics": CHARACTERISTICS, "logistics": LOGISTICS,
                         "warehouses": sorted(warehouses), "full_columns": FULL_COLUMNS, "simple_columns": SIMPLE_COLUMNS})

    def put(self, request):
        try:
            config = validate_config(request.data)
        except ValueError as exc:
            raise ValidationError(str(exc))
        SalesCalculatorPreference.objects.update_or_create(user=request.user, defaults={"config": config})
        return Response(config)


class ProductsView(AccessView):
    def get(self, request):
        # Shared data are always read from the published ClickHouse generation.
        products = read_products()
        regions = sorted({p["region"] for p in products if p["region"]})
        region = request.query_params.get("region") or self.config()["region"]
        if not region and regions:
            region = regions[0]
        rows = [p for p in products if p["region"] == region]
        today = timezone.localdate().isoformat()
        for row in rows:
            if row["calculation_date"] != today:
                row["stocks"] = None
        return Response({"products": rows, "regions": regions, "region": region,
                         "stale": any(p["calculation_date"] != today for p in rows),
                         "state": state_payload(), "can_refresh": True})


class CalculationView(AccessView):
    def result(self, request):
        config = self.config()
        region = request.data.get("region") or config["region"]
        if not region:
            raise ValidationError("Выберите регион продажи")
        products = {str(p["product_key"]): p for p in read_products(region)}
        try:
            return calculate(products, request.data.get("items", []), config), config
        except (ValueError, TypeError, KeyError) as exc:
            raise ValidationError(str(exc))

    def post(self, request):
        result, _ = self.result(request)
        return Response(serializable(result))


class RefreshView(AccessView):
    def get(self, request):
        return Response(state_payload())

    def post(self, request):
        # AccessView already requires permission to view this dashboard.
        started = request_refresh(sources=True)
        return Response(state_payload(), status=202 if started else 409)


class ExportView(CalculationView):
    def post(self, request):
        from .export import export_document
        mode = request.data.get("mode", "full")
        kind = request.data.get("format", "xlsx")
        if mode not in ("full", "simple") or kind not in ("xlsx", "pdf"):
            raise ValidationError("Некорректный формат выгрузки")
        result, config = self.result(request)
        if not config[mode + "_columns"]:
            raise ValidationError("Выберите столбцы таблицы и выгрузки")
        if not result["rows"]:
            raise ValidationError("Добавьте товары в расчёт")
        try:
            document = export_document(result, config, mode, kind)
        except (ImportError, ValueError) as exc:
            logging.getLogger("sales_calculator").exception("Export unavailable: mode=%s format=%s", mode, kind)
            return Response({"detail": f"Не удалось создать {kind.upper()}: {exc}. Проверьте зависимости и шрифты backend-контейнера."}, status=503)
        except Exception:
            logging.getLogger("sales_calculator").exception("Export failed: mode=%s format=%s", mode, kind)
            return Response({"detail": f"Не удалось создать {kind.upper()}. Подробности записаны в журнал Django (sales_calculator)."}, status=500)
        title = "Прайс" if mode == "simple" else "Коммерческое предложение"
        return FileResponse(document, as_attachment=True, filename=f"{title}.{kind}",
                            content_type="application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
