
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from dashboards.models import Dashboard
from .serializers import DashboardSerializer




class DashboardViewSet(ModelViewSet):
    queryset = Dashboard.objects.all()
    serializer_class = DashboardSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Dashboard.objects.filter(owner=self.request.user)


