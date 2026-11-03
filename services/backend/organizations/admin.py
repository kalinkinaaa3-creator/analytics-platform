from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import BaseInlineFormSet
from .models import Organization, OrganizationMembership, OrganizationSwitchLog, UserProfile
from .admin_helpers import full_name, department_name


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "theme", "postgres_schema")
    list_filter = ("is_active", "theme")

    def get_readonly_fields(self, request, obj=None):
        return ("code", "postgres_schema") if obj else ()


class ProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 1
    max_num = 1


class MembershipInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        defaults = [form for form in self.forms if form.cleaned_data.get("is_default") and not form.cleaned_data.get("DELETE")]
        if len(defaults) > 1:
            raise ValidationError("Выберите только одну организацию по умолчанию.")

    def save(self, commit=True):
        if not commit:
            return super().save(commit=False)
        # Clear the former default before saving the new one, regardless of row
        # order. The entire change stays atomic, including admin user creation.
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=self.instance.pk)
            selected = next((form for form in self.forms if form.cleaned_data.get("is_default") and not form.cleaned_data.get("DELETE")), None)
            OrganizationMembership.objects.filter(user=self.instance, is_default=True).update(is_default=False)
            result = super().save(commit=True)
            if selected is not None:
                OrganizationMembership.objects.filter(pk=selected.instance.pk).update(is_default=True)
            return result


class MembershipInline(admin.TabularInline):
    model = OrganizationMembership
    formset = MembershipInlineFormSet
    extra = 1


User = get_user_model()
admin.site.unregister(User)
if admin.site.is_registered(Group):
    admin.site.unregister(Group)


@admin.register(User)
class WorkspaceUserAdmin(UserAdmin):
    inlines = (ProfileInline, MembershipInline)
    list_display = ("username", "email", "display_full_name", "display_department", "is_staff", "is_active")
    search_fields = ("username", "email", "organization_profile__full_name", "organization_memberships__department")
    filter_horizontal = ("user_permissions",)
    fieldsets = tuple((name, {**options, "fields": tuple(
        field for field in options["fields"] if field not in ("first_name", "last_name", "groups")
    )}) for name, options in UserAdmin.fieldsets)

    @admin.display(description="ФИО")
    def display_full_name(self, obj):
        return full_name(obj)

    @admin.display(description="Department name")
    def display_department(self, obj):
        return department_name(obj)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("organization_profile").prefetch_related("organization_memberships__organization")


@admin.register(OrganizationMembership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "display_full_name", "department", "is_active", "is_default")
    list_filter = ("organization", "is_active")
    search_fields = ("user__username", "user__organization_profile__full_name", "department")
    list_select_related = ("user__organization_profile", "organization")

    @admin.display(description="ФИО")
    def display_full_name(self, obj):
        return full_name(obj.user)


@admin.register(OrganizationSwitchLog)
class SwitchLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "username", "full_name", "previous_organization_name", "organization_name", "department_name", "ip_address")
    list_filter = ("organization", "created_at")
    readonly_fields = tuple(field.name for field in OrganizationSwitchLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
