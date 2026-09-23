from rest_framework.views import APIView
from rest_framework.response import Response
from dashboards.api.permissions import CanEditIPriceDashboard, CanViewIPriceDashboard
from datasets.api.permissions import HasInternalApiKey
from datasets.models import TaraRun
from datasets.services.parsers.tara_jobs import (
    progress, create_run, kick, finish, TaraPending,
)


class TaraStatusView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request):
        run = TaraRun.objects.filter(status__in=TaraRun.ACTIVE).order_by('id').first()
        if not run:
            run = TaraRun.objects.order_by('-id').first()
        data = progress(run) if run else None
        return Response({'run': data})



class TaraCancelView(APIView):
    permission_classes = [CanEditIPriceDashboard]

    def post(self, request, run_id):
        try:
            run = TaraRun.objects.get(pk=run_id)
        except TaraRun.DoesNotExist:
            return Response({'message': 'Запуск не найден'}, status=404)
        # finish locks/rechecks the row; don't hold a coordinator lock during notifications.
        finish(run, 'cancelled', 'Загрузка Тары отменена пользователем. Полученные данные сохранены.', force=True)
        return Response({'message': 'Запуск отменён'})


class TaraInternalRunView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        key = request.data.get('request_key')
        if not isinstance(key, str) or not key or len(key) > 200:
            return Response({'message': 'Invalid request_key'}, status=400)
        try:
            run = create_run(request_key='dag:' + key, origin='dag', options={
                'workers': 5, 'classified_only': False, 'sitemap': True, 'dag_retry': True,
            })
        except TaraPending:
            return Response({'status': 'busy'}, status=409)
        kick()
        return Response(progress(run))
