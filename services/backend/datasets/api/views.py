from rest_framework.viewsets import ModelViewSet

from datasets.models import Dataset
from .serializers import DatasetSerializer

from datasets.models import DatasetRow
from .serializers import DatasetRowSerializer

class DatasetViewSet(ModelViewSet):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer

class DatasetRowViewSet(ModelViewSet):
    queryset = DatasetRow.objects.all()
    serializer_class = DatasetRowSerializer