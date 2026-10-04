from rest_framework.exceptions import PermissionDenied
from .models import OrganizationMembership, UserProfile


def available_memberships(user):
    return OrganizationMembership.objects.select_related("organization").filter(
        user=user, user__is_active=True, is_active=True, organization__is_active=True,
    ).order_by("-is_default", "organization_id")


def resolve_membership(user, organization_id=None):
    memberships = available_memberships(user)
    if organization_id is not None:
        text = str(organization_id)
        if type(organization_id) not in (str, int) or not text.isascii() or not text.isdecimal() or len(text) > 19:
            raise PermissionDenied("Некорректная организация.")
        organization_id = int(text)
        if not 0 < organization_id <= 9223372036854775807:
            raise PermissionDenied("Некорректная организация.")
        memberships = memberships.filter(organization_id=organization_id)
    membership = memberships.first()
    if membership is None:
        raise PermissionDenied("Нет доступа к организации. Обратитесь к администратору.")
    return membership


def audit_snapshot(user, organization=None):
    profile = UserProfile.objects.filter(user=user).first() if user and user.is_authenticated else None
    membership = OrganizationMembership.objects.filter(user=user, organization=organization).first() if user and user.is_authenticated and organization else None
    return {
        "organization": organization,
        "organization_name": organization.name if organization else "",
        "full_name": profile.full_name if profile else (user.get_full_name() if user and user.is_authenticated else ""),
        "department_name": membership.department if membership else "",
    }


def organization_payload(organization):
    return {"id": organization.pk, "name": organization.name, "code": organization.code, "theme": organization.theme}


def bind_request(request, user):
    membership = resolve_membership(user, request.headers.get("X-Organization-ID"))
    request.organization = membership.organization
    request.organization_membership = membership
    # Explicit identity for services which receive only user, not request.
    user._request_organization_id = membership.organization_id
    return membership.organization
