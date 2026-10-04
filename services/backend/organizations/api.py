from django.urls import path
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from dashboards.services.audit import get_client_ip
from .models import OrganizationSwitchLog
from .services import available_memberships, audit_snapshot, organization_payload, resolve_membership


class WorkspaceView(APIView):
    organization_aware = True
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "organization": organization_payload(request.organization),
            "organizations": [organization_payload(m.organization) for m in available_memberships(request.user)],
        })


class SwitchWorkspaceView(APIView):
    organization_aware = True
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from rest_framework.exceptions import ValidationError
        target_id = request.data.get("organization_id")
        if target_id is None:
            raise ValidationError({"organization_id": "Выберите организацию."})
        target = resolve_membership(request.user, target_id).organization
        if target.pk != request.organization.pk:
            OrganizationSwitchLog.objects.create(
                user=request.user, username=request.user.get_username(),
                previous_organization=request.organization,
                previous_organization_name=request.organization.name,
                ip_address=get_client_ip(request),
                **audit_snapshot(request.user, target),
            )
        return Response({"organization": organization_payload(target)})


urlpatterns = [path("", WorkspaceView.as_view()), path("switch/", SwitchWorkspaceView.as_view())]
