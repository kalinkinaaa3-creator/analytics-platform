from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Dataset
from .serializers import DatasetSerializer


class DatasetUploadView(APIView):

    def post(self, request):

        serializer = DatasetSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        dataset = serializer.save()

        return Response(
            DatasetSerializer(dataset).data,
            status=status.HTTP_201_CREATED,
        )