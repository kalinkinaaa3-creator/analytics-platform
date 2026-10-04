
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from dashboards.models import Dashboard
from .serializers import DashboardSerializer




class DashboardViewSet(ModelViewSet):
    organization_aware = True
    queryset = Dashboard.objects.all()
    serializer_class = DashboardSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Dashboard.objects.filter(owner=self.request.user, organization=self.request.organization)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, organization=self.request.organization)


