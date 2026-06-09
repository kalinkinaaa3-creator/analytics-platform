from rest_framework.response import Response
from rest_framework.decorators import api_view

@api_view(["GET"])
def list_reports(request):
    return Response({
        "reports": []
    })