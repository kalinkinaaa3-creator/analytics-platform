from rest_framework import serializers

from dashboards.models import (
    Dashboard,
    DashboardWidget
)


class DashboardWidgetSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = DashboardWidget

        fields = "__all__"


class DashboardSerializer(
    serializers.ModelSerializer
):

    widgets = DashboardWidgetSerializer(
        many=True,
        read_only=True
    )

    def validate(self, attrs):
        organization = self.context["request"].organization
        slug = attrs.get("slug", self.instance.slug if self.instance else None)
        existing = Dashboard.objects.filter(organization=organization, slug=slug)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if slug is not None and existing.exists():
            raise serializers.ValidationError({"slug": "Этот адрес уже используется в организации."})
        return attrs

    class Meta:

        model = Dashboard

        fields = "__all__"
        read_only_fields = ("organization", "owner", "component")
