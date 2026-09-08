from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Bitrix24Error(RuntimeError):
    """Base exception which never contains the webhook URL."""


class Bitrix24ConfigurationError(Bitrix24Error):
    pass


class Bitrix24RequestError(Bitrix24Error):
    pass


class Bitrix24ResponseError(Bitrix24Error):
    pass


class Bitrix24Client:
    """Small read-only Bitrix24 REST client with pagination and retries."""

    READ_ONLY_SUFFIXES = (".get", ".list", ".fields")

    def __init__(
        self,
        *,
        webhook_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self._webhook_url = (webhook_url or settings.BITRIX24_API_WEBHOOK_URL).strip()
        self._validate_webhook_url(self._webhook_url)
        self.timeout = timeout if timeout is not None else settings.BITRIX24_API_TIMEOUT
        retries = max_retries if max_retries is not None else settings.BITRIX24_API_MAX_RETRIES
        self.session = session or self._build_session(retries)

    @staticmethod
    def _validate_webhook_url(value: str) -> None:
        if not value:
            raise Bitrix24ConfigurationError("BITRIX24_API_WEBHOOK_URL is not configured.")

        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise Bitrix24ConfigurationError(
                "BITRIX24_API_WEBHOOK_URL must be an absolute HTTPS URL."
            )

    @staticmethod
    def _build_session(max_retries: int) -> requests.Session:
        retry = Retry(
            total=max(0, max_retries),
            connect=max(0, max_retries),
            read=max(0, max_retries),
            status=max(0, max_retries),
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(("POST",)),
            backoff_factor=0.5,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    @classmethod
    def _validate_method(cls, method: str) -> None:
        if not method or not method.endswith(cls.READ_ONLY_SUFFIXES):
            raise Bitrix24ConfigurationError(
                "Only read-only Bitrix24 get/list/fields methods are allowed."
            )

    def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        self._validate_method(method)
        endpoint = f"{self._webhook_url.rstrip('/')}/{method}.json"

        try:
            response = self.session.post(
                endpoint,
                json=dict(params or {}),
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise Bitrix24RequestError(
                f"Bitrix24 request failed for method {method}."
            ) from exc

        if not isinstance(payload, dict):
            raise Bitrix24ResponseError(
                f"Bitrix24 returned an invalid response for method {method}."
            )
        if payload.get("error"):
            error_code = str(payload.get("error"))[:128]
            raise Bitrix24ResponseError(
                f"Bitrix24 method {method} returned error {error_code}."
            )
        if "result" not in payload:
            raise Bitrix24ResponseError(
                f"Bitrix24 response has no result for method {method}."
            )

        return payload

    def iter_pages(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        page_params = deepcopy(dict(params or {}))
        seen_cursors: set[str] = set()

        while True:
            payload = self.call(method, page_params)
            result = payload["result"]
            if isinstance(result, list):
                items = result
            elif method == "crm.category.list" and isinstance(result, dict) and isinstance(result.get("categories"), list):
                items = result["categories"]
            elif isinstance(result, dict) and isinstance(result.get("items"), list):
                items = result["items"]
            else:
                raise Bitrix24ResponseError(
                    f"Bitrix24 result has no item list for method {method}."
                )

            yield items

            cursor = payload.get("next")
            if cursor is None and isinstance(result, dict):
                cursor = result.get("next")
            if cursor in (None, ""):
                break

            cursor_key = str(cursor)
            if cursor_key in seen_cursors:
                raise Bitrix24ResponseError(
                    f"Bitrix24 pagination repeated a cursor for method {method}."
                )
            seen_cursors.add(cursor_key)
            page_params["start"] = cursor

    def iter_items(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        for page in self.iter_pages(method, params):
            yield from page
