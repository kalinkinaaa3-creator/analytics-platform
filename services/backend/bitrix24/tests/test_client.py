from unittest import TestCase

import requests

from bitrix24.services.client import (
    Bitrix24Client,
    Bitrix24ConfigurationError,
    Bitrix24RequestError,
    Bitrix24ResponseError,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("request failed")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


class Bitrix24ClientTests(TestCase):
    webhook = "https://example.invalid/rest/1/secret"

    def test_rejects_non_https_webhook(self):
        with self.assertRaises(Bitrix24ConfigurationError):
            Bitrix24Client(webhook_url="http://example.invalid/rest/1/secret")

    def test_rejects_write_method(self):
        client = Bitrix24Client(webhook_url=self.webhook, session=FakeSession([]))

        with self.assertRaises(Bitrix24ConfigurationError):
            client.call("crm.lead.update", {"id": 1})

    def test_iter_items_supports_classic_pagination(self):
        session = FakeSession(
            [
                FakeResponse({"result": [{"ID": "1"}], "next": 50}),
                FakeResponse({"result": [{"ID": "2"}]}),
            ]
        )
        client = Bitrix24Client(webhook_url=self.webhook, session=session)

        self.assertEqual(
            list(client.iter_items("crm.lead.list", {"order": {"ID": "ASC"}})),
            [{"ID": "1"}, {"ID": "2"}],
        )
        self.assertNotIn("start", session.calls[0][1]["json"])
        self.assertEqual(session.calls[1][1]["json"]["start"], 50)

    def test_iter_items_supports_unified_api_result(self):
        session = FakeSession(
            [FakeResponse({"result": {"items": [{"id": 1}], "next": None}})]
        )
        client = Bitrix24Client(webhook_url=self.webhook, session=session)

        self.assertEqual(list(client.iter_items("crm.item.list")), [{"id": 1}])

    def test_request_exception_does_not_expose_webhook(self):
        session = FakeSession([requests.ConnectionError("network unavailable")])
        client = Bitrix24Client(webhook_url=self.webhook, session=session)

        with self.assertRaises(Bitrix24RequestError) as caught:
            client.call("crm.lead.list")

        self.assertNotIn("secret", str(caught.exception))

    def test_repeated_pagination_cursor_is_rejected(self):
        session = FakeSession(
            [
                FakeResponse({"result": [], "next": 50}),
                FakeResponse({"result": [], "next": 50}),
            ]
        )
        client = Bitrix24Client(webhook_url=self.webhook, session=session)

        with self.assertRaises(Bitrix24ResponseError):
            list(client.iter_items("crm.lead.list"))
