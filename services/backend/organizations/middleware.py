from django.http import JsonResponse
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.authentication import JWTAuthentication
from .services import bind_request
from .public_access import is_public_request


class OrganizationHeaderMiddleware:
    """Do not let legacy views with custom authentication bypass an explicit context.

    Machine integrations without an organization header keep their existing auth.
    Public links continue to derive context from their token, not the browser.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, callback, args, kwargs):
        view = getattr(callback, "cls", None)
        if not request.path.startswith("/api/v1/") or not request.headers.get("X-Organization-ID"):
            return None
        if is_public_request(request):
            return None
        if view is None or getattr(view, "authentication_classes", None):
            return None
        try:
            result = JWTAuthentication().authenticate(request)
            user = result[0] if result else request.user
            if not user.is_authenticated:
                return JsonResponse({"detail": "Требуется авторизация организации."}, status=403)
            organization = bind_request(request, user)
            if organization.code != "iplast":
                return JsonResponse({"detail": "Раздел не подключён для организации."}, status=403)
        except APIException as exc:
            return JsonResponse({"detail": str(exc.detail)}, status=exc.status_code)
