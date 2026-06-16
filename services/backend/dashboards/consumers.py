from channels.generic.websocket import AsyncJsonWebsocketConsumer


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    group_name = "dashboards"

    async def connect(self):
        user = self.scope.get("user")

        if not user or user.is_anonymous:
            await self.close()
            return

        await self.accept()

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )

    async def disconnect(self, close_code):
        if self.channel_layer:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def dashboard_updated(self, event):
        await self.send_json({
            "type": "dashboard_updated",
            "dashboard": event.get("dashboard"),
        })