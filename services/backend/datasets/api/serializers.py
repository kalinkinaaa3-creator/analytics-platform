from rest_framework import serializers

from datasets.models import Dataset, DatasetRow


class DatasetSerializer(serializers.ModelSerializer):

    class Meta:
        model = Dataset
        fields = "__all__"


class DatasetRowSerializer(serializers.ModelSerializer):

    class Meta:
        model = DatasetRow
        fields = "__all__"


class FbProjectUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class YdWordstatUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class FBPurchasesUploadSerializer(serializers.Serializer):
    use_file = serializers.FileField()


class FBTurnoverUploadSerializer(serializers.Serializer):
    turnover_file = serializers.FileField()


class FBAccreceivUploadSerializer(serializers.Serializer):
    accreceiv_file = serializers.FileField()


class IndicatorUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class PlannedSalesUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class PlanSalesUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class PlannedSalesDirectoryUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class ParserPrefixUploadSerializer(serializers.Serializer):
    file = serializers.FileField()