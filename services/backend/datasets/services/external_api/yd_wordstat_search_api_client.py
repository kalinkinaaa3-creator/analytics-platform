import requests
from django.conf import settings


class YdWordstatSearchApiError(RuntimeError):
    pass


def _headers():
    api_key = settings.YD_WORDSTAT_API_KEY.strip()
    if not api_key:
        raise YdWordstatSearchApiError("YD_WORDSTAT_API_KEY is empty")
    return {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }


def fetch_regions_tree(*, folder_id=None):
    """Fetch the v2 region tree without changing any local data."""
    base_url = settings.YD_WORDSTAT_API_BASE_URL.rstrip("/")
    body = {}
    folder_id = (
        settings.YD_WORDSTAT_FOLDER_ID if folder_id is None else folder_id
    ).strip()
    if folder_id:
        body["folderId"] = folder_id

    try:
        response = requests.post(
            f"{base_url}/getRegionsTree",
            headers=_headers(),
            json=body,
            timeout=(
                settings.YD_WORDSTAT_API_CONNECT_TIMEOUT,
                settings.YD_WORDSTAT_API_TIMEOUT,
            ),
        )
    except requests.RequestException as exc:
        raise YdWordstatSearchApiError(
            f"Wordstat Search API request failed: {exc}"
        ) from exc

    if not response.ok:
        request_id = response.headers.get("x-request-id") or response.headers.get("x-server-trace-id")
        suffix = f", request_id={request_id}" if request_id else ""
        try:
            error_data = response.json()
            error_message = error_data.get("message") if isinstance(error_data, dict) else None
        except ValueError:
            error_message = None
        if error_message:
            suffix += f", message={str(error_message)[:1000]}"
        raise YdWordstatSearchApiError(
            f"Wordstat Search API returned HTTP {response.status_code}{suffix}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise YdWordstatSearchApiError("Wordstat Search API returned invalid JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("regions"), list):
        raise YdWordstatSearchApiError("Wordstat Search API response has no regions array")
    return data
