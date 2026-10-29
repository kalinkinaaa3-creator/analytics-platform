"""Idempotent internal admission for the manual full competitor DAG."""
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from datasets.api.permissions import HasInternalApiKey
from datasets.services.parsers.tara_jobs import kick
from .iprice_pipeline import create_master


class FullCompetitorRunView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        key = serializers.CharField(max_length=200).run_validation(request.data.get('request_key'))
        try:
            run = create_master(request_key='full:' + key, full_competitors=True)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if run is None:
            return Response({'status': 'busy'}, status=409)
        kick()
        return Response({'id': run.pk, 'status': run.status, 'step': run.current_step,
                         'error': run.error, 'results': run.result.get('source_results', {})})
