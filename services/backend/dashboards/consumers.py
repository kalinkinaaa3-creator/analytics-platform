from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs
from dashboards.models import Dashboard
from dashboards.services.access import user_can_view_dashboard
from organizations.services import resolve_membership


@database_sync_to_async
def authorized_dashboard(user, organization_id, slug):
    try:
        user = get_user_model().objects.get(pk=user.pk)
        membership = resolve_membership(user, organization_id)
        dashboard = Dashboard.objects.filter(organization=membership.organization, slug=slug).first()
        return dashboard if dashboard and user_can_view_dashboard(user, dashboard) else None
    except Exception:
        return None


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    group_name = None

    async def connect(self):
        user = self.scope.get("user")
        is_authenticated = (
            user is not None
            and not user.is_anonymous
        )

        self.is_authenticated = is_authenticated
        params = parse_qs(self.scope.get("query_string", b"").decode())
        self.organization_id = params.get("organization_id", [None])[0]
        self.dashboard_slug = params.get("dashboard_slug", [None])[0]
        if is_authenticated:
            dashboard = await authorized_dashboard(user, self.organization_id, self.dashboard_slug)
            if dashboard is None:
                await self.close(code=4403)
                return
            self.organization_id = dashboard.organization_id
            self.group_name = f"organization_{dashboard.organization_id}_dashboard_{dashboard.id}"
        elif params.get("token") or self.organization_id:
            await self.close(code=4401)
            return
        else:
            # Compatibility for existing public-link clients: only Iplast events.
            self.group_name = "dashboards"

        await self.accept()

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )

    async def disconnect(self, close_code):
        if self.channel_layer and self.group_name:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def dashboard_updated(self, event):
        if self.is_authenticated and not await authorized_dashboard(self.scope["user"], self.organization_id, self.dashboard_slug):
            await self.close(code=4403)
            return
        payload = {
            key: value
            for key, value in event.items()
            if key != "type"
        }

        await self.send_json({
            "type": "dashboard_updated",
            **payload,
        })
