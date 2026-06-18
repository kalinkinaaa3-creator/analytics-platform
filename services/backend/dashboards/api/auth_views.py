from django.contrib.auth import get_user_model
from rest_framework_simplejwt.views import TokenObtainPairView

from dashboards.models import UserLoginLog
from dashboards.services.audit import get_client_ip


User = get_user_model()


class LoggingTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        username = (
            request.data.get("username")
            or request.data.get("email")
            or request.data.get("login")
        )

        response = super().post(request, *args, **kwargs)

        user = None

        if response.status_code == 200 and username:
            user = (
                User.objects
                .filter(username=username)
                .first()
            )

            if user is None:
                user = (
                    User.objects
                    .filter(email=username)
                    .first()
                )

        UserLoginLog.objects.create(
            user=user,
            username=username,
            success=response.status_code == 200,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        return response