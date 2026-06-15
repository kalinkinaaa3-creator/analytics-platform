from rest_framework.viewsets import ModelViewSet

from datasets.models import Dataset
from .serializers import DatasetSerializer

from datasets.models import DatasetRow
from .serializers import DatasetRowSerializer



import tempfile

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from datasets.services.fb_project_loader import load_fb_project_csv
from analytics.services.fb_project_sync import sync_fb_project_to_clickhouse

from dashboards.cache.invalidation import invalidate_dashboard_by_name


from rest_framework.parsers import MultiPartParser, FormParser

from .serializers import (
    FbProjectUploadSerializer,
    YdWordstatUploadSerializer,
    FBPurchasesUploadSerializer,
    FBTurnoverUploadSerializer,
)



from datasets.services.yd_wordstat_loader import load_yd_wordstat_csv
from analytics.services.yd_wordstat_sync import sync_yd_wordstat_to_clickhouse


from datasets.services.fb_purchases_loader import (
    load_fb_purchases_use_csv,
    load_fb_purchases_indicator_csv,
)
from analytics.services.fb_purchases_sync import sync_fb_purchases_to_clickhouse


from datasets.services.fb_turnover_loader import (
    load_fb_turnover_csv,
    load_fb_turnover_indicator_csv,
)
from analytics.services.fb_turnover_sync import sync_fb_turnover_to_clickhouse


from django.core.cache import cache
from django.core.management import call_command








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
        indicator_file = serializer.validated_data["indicator_file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_use:
            for chunk in use_file.chunks():
                temp_use.write(chunk)
            use_path = temp_use.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_ind:
            for chunk in indicator_file.chunks():
                temp_ind.write(chunk)
            indicator_path = temp_ind.name

        postgres_use_count = load_fb_purchases_use_csv(use_path)
        postgres_indicator_count = load_fb_purchases_indicator_csv(indicator_path)

        clickhouse_result = sync_fb_purchases_to_clickhouse()

        invalidate_dashboard_by_name("Purchases")

        return Response({
            "status": "ok",
            "postgres": {
                "fb_purchases_use": postgres_use_count,
                "fb_purchases_ind": postgres_indicator_count,
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
        indicator_file = serializer.validated_data["indicator_file"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_turnover:
            for chunk in turnover_file.chunks():
                temp_turnover.write(chunk)
            turnover_path = temp_turnover.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_ind:
            for chunk in indicator_file.chunks():
                temp_ind.write(chunk)
            indicator_path = temp_ind.name

        postgres_turnover_count = load_fb_turnover_csv(turnover_path)
        postgres_indicator_count = load_fb_turnover_indicator_csv(indicator_path)

        clickhouse_result = sync_fb_turnover_to_clickhouse()

        invalidate_dashboard_by_name("Turnover")

        call_command("warmup_turnover_cache")

        return Response({
            "status": "ok",
            "postgres": {
                "fb_turnover_use": postgres_turnover_count,
                "fb_turnover_ind": postgres_indicator_count,
            },
            "clickhouse": clickhouse_result,
            "cache": {
                "invalidated": "Turnover",
                "warmed": True,
                "command": "warmup_turnover_cache",
            },
        })