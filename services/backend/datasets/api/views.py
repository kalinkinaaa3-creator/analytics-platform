
import tempfile
import os

from datetime import datetime
from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.viewsets import ModelViewSet

from datasets.models import (
    Dataset,
    DatasetRow,
    PlanSales,
)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from datasets.services.fb_project_loader import load_fb_project_csv
from analytics.services.fb_project_sync import sync_fb_project_to_clickhouse

from dashboards.cache.invalidation import invalidate_dashboard_by_name

from dashboards.models import DashboardAccess, Dashboard

from rest_framework.parsers import MultiPartParser, FormParser

from .serializers import (
    DatasetSerializer,
    DatasetRowSerializer,
    FbProjectUploadSerializer,
    YdWordstatUploadSerializer,
    FBPurchasesUploadSerializer,
    FBTurnoverUploadSerializer,
    FBAccreceivUploadSerializer,
    IndicatorUploadSerializer,
    PlannedSalesUploadSerializer,
    PlanSalesUploadSerializer,
    PlannedSalesDirectoryUploadSerializer,

    ParserPrefixUploadSerializer,
    ProductMatchUploadSerializer,
    ProductClassificationUploadSerializer,

    ExcelUploadSerializer,

    TransportCostUploadSerializer,
    ProductCostUploadSerializer,

)



from datasets.services.yd_wordstat_loader import load_yd_wordstat_csv
from analytics.services.yd_wordstat_sync import sync_yd_wordstat_to_clickhouse


from datasets.services.fb_purchases_loader import (
    load_fb_purchases_use_csv,
    load_fb_purchases_indicator_xlsx,
)
from analytics.services.fb_purchases_sync import sync_fb_purchases_to_clickhouse


from datasets.services.fb_turnover_loader import (
    load_fb_turnover_csv,
    load_fb_turnover_indicator_xlsx,
)
from analytics.services.fb_turnover_sync import sync_fb_turnover_to_clickhouse


from django.core.management import call_command


from datasets.services.fb_accreceiv_loader import (
    load_fb_accreceiv_csv,
    load_fb_accreceiv_indicator_xlsx,
)
from analytics.services.fb_accreceiv_sync import sync_fb_accreceiv_to_clickhouse





from analytics.clickhouse.repository import ClickHouseRepository

from analytics.services.fb_purchases_prepare import (
    group_purchases_by_month,
    add_indicator_to_purchases,
    add_deviation_to_purchases,
)

from analytics.services.fb_turnover_prepare import group_turnover_monthly
from analytics.services.fb_accreceiv_prepare import group_accreceiv_monthly

from analytics.services.excel_exports import (
    export_wordstat_to_excel,
    export_purchases_to_excel,
    export_turnover_to_excel,
    export_accreceiv_to_excel,

    export_revenue_to_excel,
)


from datasets.services.planned_sales_loader import (
    load_planned_sales_csv,
    load_plan_sales_xlsx,
    load_planned_sales_directory_xlsx,
)
from analytics.services.planned_sales_sync import sync_planned_sales_to_clickhouse

from dashboards.realtime import notify_dashboard_updated


from datasets.api.permissions import HasInternalApiKey

from analytics.services.fb_project_api_pipeline import run_fb_project_api_pipeline
from analytics.services.planned_sales_api_pipeline import run_planned_sales_api_pipeline
from analytics.services.fb_purchases_api_pipeline import run_fb_purchases_api_pipeline
from analytics.services.fb_turnover_api_pipeline import run_fb_turnover_api_pipeline
from analytics.services.fb_accreceiv_api_pipeline import run_fb_accreceiv_api_pipeline

from datasets.services.external_api.nomenclature_api_loader import (
    load_nomenclature_from_api,
)

from datasets.services.external_api.price_api_loader import (
    load_prices_from_api,
)

from datasets.services.transport_cost_loader import (
    load_transport_cost_from_excel,
)

from datasets.services.product_cost_loader import (
    load_product_cost_from_excel,
)

from rest_framework.exceptions import NotFound, PermissionDenied
from dashboards.models import DashboardPublicGroup


from datasets.services.parsers.prefix_loader import load_parser_prefixes_from_excel

from datasets.services.parsers.product_match_loader import load_product_matches_from_excel

from datasets.services.parsers.product_classification_loader import load_product_classification_from_excel




from datasets.services.external_api.yd_wordstat_ref_excel_loader import (
    load_yd_wordstat_phrase_ref_from_excel,
    load_yd_wordstat_device_ref_from_excel,
    load_yd_wordstat_iplast_region_ref_from_excel,
)

from datasets.services.external_api.yd_wordstat_region_ref_loader import (
    refresh_yd_wordstat_regions_from_api,
    refresh_yd_wordstat_regions_from_csv,
)

from analytics.services.yd_wordstat_csv_pipeline import run_yd_wordstat_csv_pipeline
from analytics.services.yd_wordstat_api_pipeline import run_yd_wordstat_api_pipeline


from django.core.cache import cache




SALES_PIPELINE_RUNNING_LOCK_KEY = "sales_pipeline_running_lock"
SALES_MANUAL_REFRESH_LOCK_KEY = "sales_api_refresh_lock"

SALES_PIPELINE_RUNNING_LOCK_TIMEOUT = 60 * 60
SALES_MANUAL_REFRESH_LOCK_TIMEOUT = 60 * 60






def get_public_group_or_404(token):
    try:
        group = DashboardPublicGroup.objects.prefetch_related(
            "items__dashboard"
        ).get(token=token)
    except DashboardPublicGroup.DoesNotExist:
        raise NotFound("Public group not found")

    if not group.is_valid():
        raise PermissionDenied("Public group expired")

    return group


def check_public_dashboard_access(token, dashboard_slug):
    group = get_public_group_or_404(token)

    group_item = (
        group.items
        .select_related("dashboard")
        .filter(dashboard__slug=dashboard_slug)
        .first()
    )

    if group_item is None:
        raise PermissionDenied("Dashboard is not available in this public group")

    return group_item









class DatasetViewSet(ModelViewSet):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer

class DatasetRowViewSet(ModelViewSet):
    queryset = DatasetRow.objects.all()
    serializer_class = DatasetRowSerializer





class FbProjectUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = FbProjectUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        if not uploaded_file:
            return Response(
                {"error": "file is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)

            temp_path = temp_file.name

        postgres_count = load_fb_project_csv(temp_path)
        projects_count = sync_fb_project_to_clickhouse()

        invalidate_dashboard_by_name("Projects")

        return Response({
            "status": "ok",
            "postgres_rows": postgres_count,
            "projects_count": projects_count,
        })
    



class YdWordstatUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = YdWordstatUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        if not uploaded_file:
            return Response(
                {"error": "file is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)

            temp_path = temp_file.name

        postgres_count = load_yd_wordstat_csv(temp_path)
        clickhouse_count = sync_yd_wordstat_to_clickhouse()

        invalidate_dashboard_by_name("Wordstat")

        return Response({
            "status": "ok",
            "postgres_rows": postgres_count,
            "clickhouse_rows": clickhouse_count,
        })
    




class FBPurchasesUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = FBPurchasesUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        use_file = serializer.validated_data["use_file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_use:
            for chunk in use_file.chunks():
                temp_use.write(chunk)
            use_path = temp_use.name

        postgres_use_count = load_fb_purchases_use_csv(use_path)

        clickhouse_result = sync_fb_purchases_to_clickhouse()

        invalidate_dashboard_by_name("Purchases")

        return Response({
            "status": "ok",
            "postgres": {
                "fb_purchases_use": postgres_use_count,
            },
            "clickhouse": clickhouse_result,
        })
    



class FBTurnoverUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = FBTurnoverUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        turnover_file = serializer.validated_data["turnover_file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_turnover:
            for chunk in turnover_file.chunks():
                temp_turnover.write(chunk)
            turnover_path = temp_turnover.name

        postgres_turnover_count = load_fb_turnover_csv(turnover_path)

        clickhouse_result = sync_fb_turnover_to_clickhouse()

        invalidate_dashboard_by_name("Turnover")

        call_command("warmup_turnover_cache")

        return Response({
            "status": "ok",
            "postgres": {
                "fb_turnover_use": postgres_turnover_count,
            },
            "clickhouse": clickhouse_result,
            "cache": {
                "invalidated": "Turnover",
                "warmed": True,
                "command": "warmup_turnover_cache",
            },
        })




class FBAccreceivUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = FBAccreceivUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        accreceiv_file = serializer.validated_data["accreceiv_file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_accreceiv:
            for chunk in accreceiv_file.chunks():
                temp_accreceiv.write(chunk)
            accreceiv_path = temp_accreceiv.name

        postgres_accreceiv_count = load_fb_accreceiv_csv(accreceiv_path)

        clickhouse_result = sync_fb_accreceiv_to_clickhouse()

        invalidate_dashboard_by_name("Accreceiv")

        return Response({
            "status": "ok",
            "postgres": {
                "fb_accreceiv_use": postgres_accreceiv_count,
            },
            "clickhouse": clickhouse_result,
        })
    




class FBAccreceivIndicatorUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = IndicatorUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name

        postgres_result = load_fb_accreceiv_indicator_xlsx(temp_path)
        clickhouse_result = sync_fb_accreceiv_to_clickhouse()

        invalidate_dashboard_by_name("Accreceiv")

        return Response({
            "status": "ok",
            "postgres": postgres_result,
            "clickhouse": clickhouse_result,
        })


class FBPurchasesIndicatorUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = IndicatorUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name

        postgres_result = load_fb_purchases_indicator_xlsx(temp_path)
        clickhouse_result = sync_fb_purchases_to_clickhouse()

        invalidate_dashboard_by_name("Purchases")

        return Response({
            "status": "ok",
            "postgres": postgres_result,
            "clickhouse": clickhouse_result,
        })


class FBTurnoverIndicatorUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = IndicatorUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name

        postgres_result = load_fb_turnover_indicator_xlsx(temp_path)
        clickhouse_result = sync_fb_turnover_to_clickhouse()

        invalidate_dashboard_by_name("Turnover")
        call_command("warmup_turnover_cache")

        return Response({
            "status": "ok",
            "postgres": postgres_result,
            "clickhouse": clickhouse_result,
            "cache": {
                "warmed": True,
                "command": "warmup_turnover_cache",
            },
        })







class WordstatExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_yd_wordstat_rows(filters)

        return export_wordstat_to_excel(rows)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)
    


class FBPurchasesExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_fb_purchases_use_rows(filters)
        indicator_rows = repo.fetch_fb_purchases_indicator_rows(filters)

        purchases_list = group_purchases_by_month(rows)
        purchases_list = add_indicator_to_purchases(purchases_list, indicator_rows)
        purchases_list = add_deviation_to_purchases(purchases_list)

        return export_purchases_to_excel(purchases_list)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)


class FBTurnoverExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_fb_turnover_use_rows(filters)

        turnover_list = group_turnover_monthly(rows)

        return export_turnover_to_excel(turnover_list)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)


class FBAccreceivExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_fb_accreceiv_use_rows(filters)

        accreceiv_list = group_accreceiv_monthly(rows)

        return export_accreceiv_to_excel(accreceiv_list)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)





class PublicFBTurnoverExportView(APIView):
    authentication_classes = []
    permission_classes = []
    def post(self, request, token):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="turnover",
        )
        filters = request.data or {}
        repo = ClickHouseRepository()
        rows = repo.fetch_fb_turnover_use_rows(filters)
        turnover_list = group_turnover_monthly(rows)
        return export_turnover_to_excel(turnover_list)
    def get(self, request, token):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="turnover",
        )
        filters = {}
        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        repo = ClickHouseRepository()
        rows = repo.fetch_fb_turnover_use_rows(filters)
        turnover_list = group_turnover_monthly(rows)
        return export_turnover_to_excel(turnover_list)


class PublicFBAccreceivExportView(APIView):
    authentication_classes = []
    permission_classes = []
    def post(self, request, token):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="accreceiv",
        )
        filters = request.data or {}
        repo = ClickHouseRepository()
        rows = repo.fetch_fb_accreceiv_use_rows(filters)
        accreceiv_list = group_accreceiv_monthly(rows)
        return export_accreceiv_to_excel(accreceiv_list)
    def get(self, request, token):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="accreceiv",
        )
        filters = {}
        for key in request.query_params.keys():
            values = request.query_params.getlist(key)
            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]
        repo = ClickHouseRepository()
        rows = repo.fetch_fb_accreceiv_use_rows(filters)
        accreceiv_list = group_accreceiv_monthly(rows)
        return export_accreceiv_to_excel(accreceiv_list)


class PublicFBPurchasesExportView(APIView):
    authentication_classes = []
    permission_classes = []
    def _get_filters_from_query_params(self, request):
        filters = {}
        for key in request.query_params.keys():
            values = request.query_params.getlist(key)
            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]
        return filters
    def _get_filters_from_body(self, request):
        return request.data or {}
    def _export(self, token, filters):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="purchases",
        )
        repo = ClickHouseRepository()
        rows = repo.fetch_fb_purchases_use_rows(filters)
        indicator_rows = repo.fetch_fb_purchases_indicator_rows(filters)
        purchases_list = group_purchases_by_month(rows)
        purchases_list = add_indicator_to_purchases(purchases_list, indicator_rows)
        purchases_list = add_deviation_to_purchases(purchases_list)
        return export_purchases_to_excel(purchases_list)
    def get(self, request, token):
        filters = self._get_filters_from_query_params(request)
        return self._export(token=token, filters=filters)
    def post(self, request, token):
        filters = self._get_filters_from_body(request)
        return self._export(token=token, filters=filters)














class PlannedSalesUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = PlannedSalesUploadSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name

        postgres_count = load_planned_sales_csv(temp_path)
        clickhouse_result = sync_planned_sales_to_clickhouse()

        invalidate_dashboard_by_name("PlannedSales")
        notify_dashboard_updated("PlannedSales")

        return Response({
            "status": "ok",
            "postgres": {
                "planned_sales": postgres_count,
            },
            "clickhouse": clickhouse_result,
        })


class PlanSalesUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = PlanSalesUploadSerializer

    def post(self, request):
        dashboard = Dashboard.objects.filter(name="PlannedSales").first()

        if not dashboard:
            return Response(
                {"error": "PlannedSales dashboard not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        can_edit = DashboardAccess.objects.filter(
            user=request.user,
            dashboard=dashboard,
            can_edit=True,
        ).exists()

        if not can_edit:
            return Response(
                {"error": "No edit permission"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".xlsx",
        ) as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)

            temp_path = temp_file.name

        try:
            postgres_count = load_plan_sales_xlsx(temp_path)

            clickhouse_result = sync_planned_sales_to_clickhouse()

            invalidate_dashboard_by_name("PlannedSales")
            notify_dashboard_updated("PlannedSales")

            return Response({
                "status": "ok",
                "postgres": {
                    "plan_sales": postgres_count,
                },
                "clickhouse": clickhouse_result,
            })

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class PlannedSalesDirectoryUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = PlannedSalesDirectoryUploadSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name

        postgres_count = load_planned_sales_directory_xlsx(temp_path)
        clickhouse_result = sync_planned_sales_to_clickhouse()

        invalidate_dashboard_by_name("PlannedSales")
        notify_dashboard_updated("PlannedSales")

        return Response({
            "status": "ok",
            "postgres": {
                "planned_sales_directory": postgres_count,
            },
            "clickhouse": clickhouse_result,
        })




class PlannedSalesSavePlanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        field = request.data.get("field")
        value = request.data.get("value")
        row_date = request.data.get("date")
        id_directory = request.data.get("id_directory")

        dashboard = Dashboard.objects.filter(name="PlannedSales").first()

        if not dashboard:
            return Response(
                {"error": "PlannedSales dashboard not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        can_edit = DashboardAccess.objects.filter(
            user=request.user,
            dashboard=dashboard,
            can_edit=True,
        ).exists()

        if not can_edit:
            return Response(
                {"error": "No edit permission"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if field == "projection":
            field = "projection_s"

        if field not in ("plan", "projection_s"):
            return Response(
                {"error": "field must be plan or projection_s"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not row_date or not id_directory:
            return Response(
                {"error": "date and id_directory are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PlanSales.objects.update_or_create(
            date=row_date,
            id_directory=int(id_directory),
            defaults={
                field: value or 0,
            },
        )

        clickhouse_result = sync_planned_sales_to_clickhouse()

        invalidate_dashboard_by_name("PlannedSales")
        notify_dashboard_updated("PlannedSales")

        return Response({
            "status": "ok",
            "clickhouse": clickhouse_result,
        })
    




class FbProjectApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_fb_project_api_pipeline()
        return Response(result)
    

class PlannedSalesApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        running_lock_acquired = cache.add(
            SALES_PIPELINE_RUNNING_LOCK_KEY,
            True,
            timeout=SALES_PIPELINE_RUNNING_LOCK_TIMEOUT,
        )

        if not running_lock_acquired:
            return Response(
                {
                    "status": "locked",
                    "message": "Обновление данных уже выполняется",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            result = run_planned_sales_api_pipeline()
            return Response(result)

        finally:
            cache.delete(SALES_PIPELINE_RUNNING_LOCK_KEY)



class SalesRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        manual_lock_acquired = cache.add(
            SALES_MANUAL_REFRESH_LOCK_KEY,
            True,
            timeout=SALES_MANUAL_REFRESH_LOCK_TIMEOUT,
        )

        if not manual_lock_acquired:
            return Response(
                {
                    "status": "locked",
                    "message": "Обновление данных уже выполнено за текущий час",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        running_lock_acquired = cache.add(
            SALES_PIPELINE_RUNNING_LOCK_KEY,
            True,
            timeout=SALES_PIPELINE_RUNNING_LOCK_TIMEOUT,
        )

        if not running_lock_acquired:
            return Response(
                {
                    "status": "locked",
                    "message": "Обновление данных уже выполняется",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            result = run_planned_sales_api_pipeline()
            return Response(result)

        finally:
            cache.delete(SALES_PIPELINE_RUNNING_LOCK_KEY)



class FBPurchasesApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_fb_purchases_api_pipeline()

        return Response(result)
    

class FBTurnoverApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_fb_turnover_api_pipeline()

        return Response(result)
    

class FBAccreceivApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_fb_accreceiv_api_pipeline()

        return Response(result)
    



class TableHealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        call_command("check_table_health")

        return Response({
            "status": "ok",
            "command": "check_table_health",
        })


class ProcessKillView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        call_command("kill_long_running_processes")

        return Response({
            "status": "ok",
            "command": "kill_long_running_processes",
        })
    







class ParserPrefixUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ParserPrefixUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        result = load_parser_prefixes_from_excel(uploaded_file)

        return Response(result)




class ProductMatchUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ProductMatchUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        result = load_product_matches_from_excel(uploaded_file)

        return Response(result, status=status.HTTP_200_OK)
    



class ProductClassificationUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ProductClassificationUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        result = load_product_classification_from_excel(uploaded_file)

        return Response(result, status=status.HTTP_200_OK)




class ProductUrlControlExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        file_path = os.path.join(
            settings.BASE_DIR,
            "media",
            "datasets",
            "parser_product_url_control_latest.xlsx",
        )

        if not os.path.exists(file_path):
            raise Http404(
                "Export file not found. Run build_product_url_control_export first."
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"parser_product_url_control_{timestamp}.xlsx"

        file_obj = open(file_path, "rb")

        return FileResponse(
            file_obj,
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )







class BaseYdWordstatRefExcelUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ExcelUploadSerializer
    loader_func = None

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        temp_path = None

        try:
            suffix = os.path.splitext(uploaded_file.name)[1] or ".xlsx"

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
            ) as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)

                temp_path = temp_file.name

            result = self.loader_func(temp_path)

            return Response(result)

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)



class YdWordstatPhraseRefUploadView(BaseYdWordstatRefExcelUploadView):
    loader_func = staticmethod(load_yd_wordstat_phrase_ref_from_excel)


class YdWordstatDeviceRefUploadView(BaseYdWordstatRefExcelUploadView):
    loader_func = staticmethod(load_yd_wordstat_device_ref_from_excel)


class YdWordstatIplastRegionRefUploadView(BaseYdWordstatRefExcelUploadView):
    loader_func = staticmethod(load_yd_wordstat_iplast_region_ref_from_excel)


class YdWordstatRegionsRefreshFromApiView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        result = refresh_yd_wordstat_regions_from_api()
        return Response(result)


class YdWordstatRegionsRefreshFromCsvView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ExcelUploadSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        temp_path = None

        try:
            suffix = os.path.splitext(uploaded_file.name)[1] or ".csv"

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
            ) as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)

                temp_path = temp_file.name

            result = refresh_yd_wordstat_regions_from_csv(temp_path)

            return Response(result)

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)



class BaseYdWordstatCsvPipelineView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ExcelUploadSerializer
    source = None

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        temp_path = None

        try:
            suffix = os.path.splitext(uploaded_file.name)[1] or ".csv"

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
            ) as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)

                temp_path = temp_file.name

            result = run_yd_wordstat_csv_pipeline(
                source=self.source,
                csv_path=temp_path,
                truncate_source=True,
            )

            return Response(result)

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)


class YdWordstatAllLoadFromCsvView(BaseYdWordstatCsvPipelineView):
    source = "all"


class YdWordstatDeviceLoadFromCsvView(BaseYdWordstatCsvPipelineView):
    source = "device"


class YdWordstatRegionLoadFromCsvView(BaseYdWordstatCsvPipelineView):
    source = "region"



class YdWordstatFullLoadFromApiView(APIView):
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_yd_wordstat_api_pipeline(source=None)
        return Response(result)


class BaseYdWordstatApiPipelineView(APIView):
    permission_classes = [IsAuthenticated]
    source = None

    def post(self, request):
        result = run_yd_wordstat_api_pipeline(source=self.source)
        return Response(result)


class YdWordstatAllLoadFromApiView(BaseYdWordstatApiPipelineView):
    source = "all"


class YdWordstatDeviceLoadFromApiView(BaseYdWordstatApiPipelineView):
    source = "device"


class YdWordstatRegionLoadFromApiView(BaseYdWordstatApiPipelineView):
    source = "region"






class RevenueExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_revenue_sales_rows(filters)

        return export_revenue_to_excel(rows)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)




class NomenclatureApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = load_nomenclature_from_api()

        return Response(result)


class NomenclaturePriceApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = load_prices_from_api()
        return Response(result)


class TransportCostUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = TransportCostUploadSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        uploaded_file = serializer.validated_data["file"]

        try:
            result = load_transport_cost_from_excel(
                uploaded_file
            )

        except ValueError as exc:
            return Response(
                {
                    "status": "error",
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "ok",
                **result,
            },
            status=status.HTTP_200_OK,
        )


class ProductCostUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ProductCostUploadSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        uploaded_file = serializer.validated_data["file"]

        try:
            result = load_product_cost_from_excel(
                uploaded_file
            )

        except ValueError as exc:
            return Response(
                {
                    "status": "error",
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "ok",
                **result,
            },
            status=status.HTTP_200_OK,
        )