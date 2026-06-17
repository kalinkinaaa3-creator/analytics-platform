from django.conf import settings
from rest_framework.permissions import BasePermission


class HasInternalApiKey(BasePermission):
    def has_permission(self, request, view):
        api_key = request.headers.get("X-Internal-Api-Key")

        return bool(
            settings.INTERNAL_API_KEY
            and api_key
            and api_key == settings.INTERNAL_API_KEY
        )