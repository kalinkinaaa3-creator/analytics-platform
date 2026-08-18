from rest_framework import serializers


class LeadDashboardRequestSerializer(serializers.Serializer):
    date_start = serializers.DateField()
    date_end = serializers.DateField()
    department_ids = serializers.ListField(
        child=serializers.IntegerField(),
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
    status_ids = serializers.ListField(
        child=serializers.CharField(max_length=128),
        required=False,
        default=list,
    )
    group_by = serializers.ChoiceField(
        choices=("day", "week", "month", "quarter", "year"),
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


class ManagerTrackingUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
