from rest_framework.views import (
    APIView
)

from rest_framework.response import (
    Response
)

from dashboards.services.dashboard_builder import (
    build_dashboard
)


class DashboardBuilderView(
    APIView
):

    def get(
        self,
        request,
        dashboard_id
    ):

        result = build_dashboard(
            dashboard_id
        )

        return Response(
            result
        )