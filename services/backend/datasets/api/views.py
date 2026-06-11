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

from .serializers import FbProjectUploadSerializer



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