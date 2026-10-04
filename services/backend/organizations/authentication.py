from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication
from .services import bind_request
from .public_access import is_public_request


def check_workspace(request, user):
    if is_public_request(request):
        return  # Existing public links are authorized by their own token.
    organization = bind_request(request, user)
    if organization.code == "iplast":
        return
    # Existing integrations are owned by Iplast. New organizations are fail-closed:
    # only explicitly organization-aware endpoints can execute in their context.
    view = request.parser_context.get("view") if request.parser_context else None
    if not getattr(view, "organization_aware", False):
        raise PermissionDenied("Этот раздел не подключён для выбранной организации.")


class OrganizationJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            check_workspace(request, result[0])
        return result


class OrganizationSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            check_workspace(request, result[0])
        return result
