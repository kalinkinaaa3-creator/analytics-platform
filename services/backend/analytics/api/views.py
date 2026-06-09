from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.services.dataset_stats import (
    dataset_statistics
)


class DatasetStatsView(APIView):

    def get(self, request, dataset_id):

        result = dataset_statistics(
            dataset_id
        )

        return Response(result)