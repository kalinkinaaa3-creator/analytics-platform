from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notify_dashboard_updated(
    dashboard_name: str,
    **payload,
):
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        "dashboards",
        {
            "type": "dashboard.updated",
            "dashboard": dashboard_name,
            **payload,
        },
    )
