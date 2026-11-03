from django.conf import settings
from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from organizations.models import Organization, OrganizationMembership
from .models import DashboardAccess, DashboardDepartmentGroup, DashboardDepartmentExclusion
from .services.department_access import reconciling, sync_user_access, sync_all_access


@receiver(post_save, sender=DashboardDepartmentGroup)
@receiver(post_delete, sender=DashboardDepartmentGroup)
def group_changed(sender, instance, using, **kwargs):
    if not kwargs.get("raw"):
        sync_all_access(using)


@receiver(post_save, sender=OrganizationMembership)
@receiver(post_delete, sender=OrganizationMembership)
def membership_changed(sender, instance, using, **kwargs):
    if not kwargs.get("raw"):
        for user_id in sorted({instance.user_id, getattr(instance, "_previous_user_id", instance.user_id)}):
            sync_user_access(user_id, using)


@receiver(pre_save, sender=OrganizationMembership)
def remember_membership_user(sender, instance, using, **kwargs):
    instance._previous_user_id = sender.objects.using(using).filter(pk=instance.pk).values_list("user_id", flat=True).first() or instance.user_id


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def user_changed(sender, instance, using, **kwargs):
    if not kwargs.get("raw"):
        sync_user_access(instance.pk, using)


@receiver(post_save, sender=Organization)
def organization_changed(sender, instance, using, **kwargs):
    if not kwargs.get("raw"):
        sync_all_access(using)


@receiver(post_save, sender=DashboardAccess)
def manual_access_saved(sender, instance, using, **kwargs):
    if reconciling.get() or kwargs.get("raw"):
        return
    with transaction.atomic(using=using):
        DashboardAccess.objects.using(using).filter(pk=instance.pk).update(manual_can_view=instance.can_view, manual_can_edit=instance.can_edit)
        DashboardDepartmentExclusion.objects.using(using).filter(user_id=instance.user_id, dashboard_id=instance.dashboard_id).delete()
        sync_user_access(instance.user_id, using)


@receiver(post_delete, sender=DashboardAccess)
def personal_access_deleted(sender, instance, using, origin=None, **kwargs):
    # Ignore cascades from a deleted user/dashboard and our own reconciliation.
    origin_model = getattr(origin, "model", type(origin))
    if not reconciling.get() and origin_model is DashboardAccess:
        DashboardDepartmentExclusion.objects.using(using).get_or_create(user_id=instance.user_id, dashboard_id=instance.dashboard_id)
