
import tempfile

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
)


from datasets.services.planned_sales_loader import (
    load_planned_sales_csv,
    load_plan_sales_csv,
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

    def get(self, request):
        filters = request.GET.dict()

        repo = ClickHouseRepository()

        rows = repo.fetch_yd_wordstat_rows(filters)

        return export_wordstat_to_excel(rows)
    


class FBPurchasesExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        filters = request.GET.dict()

        repo = ClickHouseRepository()

        rows = repo.fetch_fb_purchases_use_rows(filters)
        indicator_rows = repo.fetch_fb_purchases_indicator_rows(filters)

        purchases_list = group_purchases_by_month(rows)
        purchases_list = add_indicator_to_purchases(purchases_list, indicator_rows)
        purchases_list = add_deviation_to_purchases(purchases_list)

        return export_purchases_to_excel(purchases_list)


class FBTurnoverExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        filters = request.GET.dict()

        repo = ClickHouseRepository()

        rows = repo.fetch_fb_turnover_use_rows(filters)

        turnover_list = group_turnover_monthly(rows)

        return export_turnover_to_excel(turnover_list)


class FBAccreceivExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        filters = request.GET.dict()

        repo = ClickHouseRepository()

        rows = repo.fetch_fb_accreceiv_use_rows(filters)

        accreceiv_list = group_accreceiv_monthly(rows)

        return export_accreceiv_to_excel(accreceiv_list)









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
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name

        postgres_count = load_plan_sales_csv(temp_path)
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
        result = run_planned_sales_api_pipeline()

        return Response(result)
    

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