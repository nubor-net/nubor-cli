from __future__ import annotations

import time
from types import SimpleNamespace
from unittest import mock

import click
import pytest

from nubor.core.api import ApiClient, ApiConnection, ApiResource, StoredCredentials
from nubor.core.config import _private_auth_url, _validate_private_connection


def test_api_rejects_plain_http_except_loopback():
    with pytest.raises(click.ClickException):
        ApiClient("roger", "http://api.nubor.net")
    assert ApiClient("roger", "http://127.0.0.1:8080").api_url.endswith(":8080")


def test_private_break_glass_rejects_public_keystone():
    conn = SimpleNamespace(
        config=SimpleNamespace(get_auth_args=lambda: {"auth_url": "https://keystone.nubor.net/v3"})
    )
    with pytest.raises(click.ClickException):
        _validate_private_connection(conn)

    assert _private_auth_url("http://10.0.2.72:5000/v3")
    assert not _private_auth_url("https://keystone.nubor.net/v3")


def test_api_request_sends_keystone_token_only_in_authorization(monkeypatch):
    client = ApiClient("roger")
    stored = StoredCredentials("keystone-secret", "2030-01-01", "refresh-secret", time.time())
    monkeypatch.setattr(client, "_stored", lambda: stored)
    call = mock.Mock(return_value=([{"id": "one"}], {}, 200))
    monkeypatch.setattr(client, "_json_request", call)

    assert client.request("/v1/instances") == [{"id": "one"}]
    assert call.call_args.kwargs["headers"] == {"Authorization": "Bearer keystone-secret"}
    assert "refresh-secret" not in str(call.call_args)


def test_gpu_flavor_becomes_boot_only_attachment(monkeypatch):
    conn = ApiConnection("roger")
    response = {
        "id": "server-1",
        "name": "opencode-gpu",
        "status": "BUILD",
        "addresses": {},
    }
    call = mock.Mock(return_value=response)
    monkeypatch.setattr(conn.client, "request", call)

    server = conn.create_instance(
        name="opencode-gpu",
        flavor=ApiResource(id="gpu-id", name="gpu.k8s.node"),
        image=ApiResource(id="image-id", name="ubuntu"),
        network=ApiResource(id="network-id", name="default"),
        key_name=None,
        static_private=True,
        static_external=True,
        external_network=ApiResource(id="external-id", name="public"),
    )

    assert server.id == "server-1"
    payload = call.call_args.kwargs["data"]
    assert payload["accelerators"] == [{"type": "nvidia-rtx-3080", "count": 1}]
    assert payload["network"]["private_address"] == "static"
    assert payload["network"]["external_address"] == "static"
