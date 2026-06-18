from dashboards.models import DashboardViewLog


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def log_dashboard_view(
    request,
    dashboard,
    filters=None,
    access_type="auth",
    public_access=None,
):
    DashboardViewLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        dashboard=dashboard,
        public_access=public_access,
        access_type=access_type,
        filters=filters or {},
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )