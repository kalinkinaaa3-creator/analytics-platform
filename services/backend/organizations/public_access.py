import re


# Only the existing token-based public routes are exempt from workspace selection.
# A private dashboard may itself have the slug "public".
_PUBLIC_ROUTE = re.compile(
    r"^/api/v1/(?:dashboards|datasets)/public(?:-group)?/"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/"
)


def is_public_request(request):
    return bool(_PUBLIC_ROUTE.match(request.path_info))
