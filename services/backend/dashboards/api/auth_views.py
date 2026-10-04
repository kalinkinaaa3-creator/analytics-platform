from django.contrib.auth import get_user_model
from rest_framework_simplejwt.views import TokenObtainPairView

from dashboards.models import UserLoginLog
from dashboards.services.audit import get_client_ip
from organizations.services import audit_snapshot, available_memberships, organization_payload, resolve_membership


User = get_user_model()


class LoggingTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        username = str(request.data.get("username") or "")[:255]
        user = None
        organization = None
        success = False
        try:
            response = super().post(request, *args, **kwargs)
            user = User.objects.get(username=username)
            organization = resolve_membership(user).organization
            response.data["organization"] = organization_payload(organization)
            response.data["organizations"] = [organization_payload(m.organization) for m in available_memberships(user)]
            success = True
            return response
        finally:
            UserLoginLog.objects.create(
                user=user, username=username, success=success,
                ip_address=get_client_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", ""),
                **audit_snapshot(user, organization),
            )
