"""Read-only directory of departments and their users in the auth admin."""
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .admin_helpers import full_name
from .models import OrganizationMembership


@admin.register(Group)
class DepartmentDirectoryAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        # These are live department memberships, not Django permission groups.
        return [path("", self.admin_site.admin_view(self.changelist_view), name="auth_group_changelist")]

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        memberships = OrganizationMembership.objects.exclude(department="").select_related(
            "organization", "user__organization_profile",
        ).order_by("department", "organization__name", "user__username")
        groups = {}
        can_view_users = request.user.has_perm("auth.view_user") or request.user.has_perm("auth.change_user")
        for membership in memberships:
            key = (membership.organization_id, membership.department)
            group = groups.setdefault(key, {"name": membership.department, "organization": membership.organization.name, "users": []})
            group["users"].append({
                "username": membership.user.username, "full_name": full_name(membership.user),
                "active": membership.is_active and membership.user.is_active and membership.organization.is_active,
                "url": reverse("admin:auth_user_change", args=[membership.user_id]) if can_view_users else None,
            })
        query = request.GET.get("q", "").strip()
        rows = list(groups.values())
        if query:
            term = query.casefold()
            rows = [group for group in rows if term in " ".join([
                group["name"], group["organization"],
                *[f'{user["username"]} {user["full_name"]}' for user in group["users"]],
            ]).casefold()]
        page = Paginator(rows, 50).get_page(request.GET.get("p"))
        context = {
            **self.admin_site.each_context(request), "title": "Groups", "opts": self.model._meta,
            "page": page, "query": query, "media": self.media,
            **(extra_context or {}),
        }
        return TemplateResponse(request, "admin/organizations/department_groups.html", context)
