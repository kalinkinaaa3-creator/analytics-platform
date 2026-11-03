"""Materialize department grants while preserving manual rights and exclusions."""
from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.auth import get_user_model
from django.db import transaction

from dashboards.models import DashboardAccess, DashboardDepartmentGroup, DashboardDepartmentExclusion
from organizations.models import OrganizationMembership

reconciling = ContextVar("reconciling_department_access", default=False)


@contextmanager
def reconciliation():
    token = reconciling.set(True)
    try:
        yield
    finally:
        reconciling.reset(token)


def sync_user_access(user_id, using="default"):
    with transaction.atomic(using=using), reconciliation():
        user = get_user_model().objects.using(using).select_for_update().filter(pk=user_id).first()
        if user is None:
            return
        memberships = dict(OrganizationMembership.objects.using(using).filter(
            user_id=user_id, is_active=True, organization__is_active=True,
        ).values_list("organization_id", "department"))
        excluded = set(DashboardDepartmentExclusion.objects.using(using).filter(user_id=user_id).values_list("dashboard_id", flat=True))
        grants = {}
        if user.is_active:
            for group in DashboardDepartmentGroup.objects.using(using).filter(is_active=True).select_related("dashboard"):
                if group.dashboard_id not in excluded and memberships.get(group.dashboard.organization_id) in group.departments:
                    previous = grants.get(group.dashboard_id, (False, False))
                    grants[group.dashboard_id] = (previous[0] or group.can_view, previous[1] or group.can_edit)
        existing = {access.dashboard_id: access for access in DashboardAccess.objects.using(using).filter(user_id=user_id)}
        for dashboard_id in existing.keys() | grants.keys():
            access = existing.get(dashboard_id)
            inherited = grants.get(dashboard_id)
            manual = access is not None and access.manual_can_view is not None
            if inherited is None and not manual:
                if access:
                    access.delete(using=using)
                continue
            values = {
                "can_view": bool((access.manual_can_view if manual else False) or (inherited and inherited[0])),
                "can_edit": bool((access.manual_can_edit if manual else False) or (inherited and inherited[1])),
                "from_department_group": inherited is not None,
            }
            if access:
                DashboardAccess.objects.using(using).filter(pk=access.pk).update(**values)
            else:
                DashboardAccess.objects.using(using).bulk_create([DashboardAccess(user_id=user_id, dashboard_id=dashboard_id, **values)])


def sync_all_access(using="default"):
    for user_id in get_user_model().objects.using(using).order_by("pk").values_list("pk", flat=True).iterator():
        sync_user_access(user_id, using=using)
