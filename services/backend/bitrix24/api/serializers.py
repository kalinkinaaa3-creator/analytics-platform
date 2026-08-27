from rest_framework import serializers


class LeadDashboardRequestSerializer(serializers.Serializer):
    date_start = serializers.DateField()
    date_end = serializers.DateField()
    department_names = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        default=list,
    )
    manager_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )
    source_ids = serializers.ListField(
        child=serializers.CharField(max_length=128),
        required=False,
        default=list,
    )
    semantic_status_ids = serializers.ListField(
        child=serializers.CharField(max_length=32),
        required=False,
        default=list,
    )
    status_ids = serializers.ListField(
        child=serializers.CharField(max_length=128),
        required=False,
        default=list,
    )
    exclude_untracked_department = serializers.BooleanField(default=True)
    group_by = serializers.ChoiceField(
        choices=("day", "week", "month", "year"),
        default="month",
    )

    def validate(self, attrs):
        if attrs["date_end"] < attrs["date_start"]:
            raise serializers.ValidationError(
                {"date_end": "Дата окончания не может быть раньше даты начала."}
            )
        return attrs


class LeadDashboardRowsRequestSerializer(LeadDashboardRequestSerializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=10, max_value=200, default=50)
    segment_type = serializers.ChoiceField(
        choices=("dashboard_status", "source", "manager", "low_quality_status"),
        required=False,
        allow_null=True,
        default=None,
    )
    segment_key = serializers.CharField(required=False, allow_blank=True, default="")
    segment_keys = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        default=list,
    )
    period = serializers.DateField(required=False, allow_null=True, default=None)
    sort_by = serializers.ChoiceField(
        choices=(
            "lead_id", "title", "company_name", "manager_name", "status_name",
            "source_name", "source_created_at", "source_updated_at",
            "first_processing_at", "opportunity", "processing_duration_days",
        ),
        default="source_created_at",
    )
    sort_direction = serializers.ChoiceField(choices=("asc", "desc"), default="desc")


class ManagerTrackingUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
