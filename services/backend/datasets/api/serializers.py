from rest_framework import serializers

from datasets.models import Dataset
from datasets.models import DatasetRow

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