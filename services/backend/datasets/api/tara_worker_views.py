import secrets
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView
from rest_framework.response import Response
from datasets.models import TaraFetch, TaraRun
from datasets.services.parsers import tara_remote


class WorkerPermission(BasePermission):
    def has_permission(self, request, view):
        key = getattr(settings, 'TARA_WORKER_KEY', '')
        return bool(key and secrets.compare_digest(
            request.headers.get('X-Tara-Worker-Key', ''), key))


class TaraWorkerClaimView(APIView):
    authentication_classes = []
    permission_classes = [WorkerPermission]

    def post(self, request):
        owner = request.data.get('owner')
        ready = request.data.get('ready')
        if not isinstance(owner,str) or len(owner)!=32 or any(c not in '0123456789abcdef' for c in owner) or type(ready) is not bool:
            return Response({'message':'Invalid worker'}, status=400)
        try:
            workspace = tara_remote.worker_workspace()
            tasks = tara_remote.claim(owner, ready, pull=request.data.get('pull', True) is True, workspace=workspace)
        except ValueError as exc:
            return Response({'message':str(exc)}, status=409)
        run_model = workspace.model('TaraRun') if workspace else TaraRun
        if ready and run_model.objects.filter(status='queued').exists():
            from datasets.services.parsers.tara_jobs import kick
            kick()
        return Response({'tasks':tasks})


class TaraWorkerResultView(APIView):
    authentication_classes = []
    permission_classes = [WorkerPermission]

    def post(self, request, task_id):
        if int(request.META.get('CONTENT_LENGTH') or 0)>9*1024*1024:
            return Response({'message':'Response too large'},status=413)
        try:
            workspace = tara_remote.result_workspace(task_id, request.data.get('token'))
            tara_remote.complete(task_id, request.data.get('token'), request.data.get('payload'), workspace=workspace)
        except ObjectDoesNotExist:
            return Response({'message':'Task not found'},status=404)
        except ValueError as exc:
            return Response({'message':str(exc)},status=409)
        return Response({'accepted':True})
