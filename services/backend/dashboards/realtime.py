from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notify_dashboard_updated(
    dashboard_name: str,
    organization_id=None,
    **payload,
):
    from dashboards.models import Dashboard
    from organizations.models import legacy_organization_id
    from django.db.models import Q
    legacy_id = legacy_organization_id()
    organization_id = legacy_id if organization_id is None else organization_id
    channel_layer = get_channel_layer()
    event = {
            "type": "dashboard.updated",
            "dashboard": dashboard_name,
            **payload,
        }
    aliases = {"SEOAnalytics": "seo-analytics", "ContextAnalytics": "context-analytics", "CRMAnalytics": "crm-analytics", "LeadGeneration": "lead-generation", "IPrice": "iprice", "SalesCalculator": "commercial-price"}
    dashboards = Dashboard.objects.filter(organization_id=organization_id).filter(
        Q(name=dashboard_name) | Q(slug=aliases.get(dashboard_name, ""))
    )
    for dashboard in dashboards:
        async_to_sync(channel_layer.group_send)(f"organization_{organization_id}_dashboard_{dashboard.id}", event)
    if organization_id == legacy_id:
        async_to_sync(channel_layer.group_send)("dashboards", event)
