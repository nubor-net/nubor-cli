"""HTTPS transport for api.nubor.net and a small openstacksdk-compatible facade."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import click
import keyring
import openstack.exceptions

DEFAULT_API_URL = "https://api.nubor.net"
DEFAULT_ISSUER = "https://auth.home.rogersbernat.me"
DEFAULT_CLIENT_ID = "nubor-cli"
SCOPES = "openid profile email groups offline_access"
MAX_SESSION_SECONDS = 8 * 60 * 60


class ApiResource(SimpleNamespace):
    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


def _resource(value: dict[str, Any]) -> ApiResource:
    return ApiResource(**value)


@dataclass
class StoredCredentials:
    keystone_token: str
    keystone_expires_at: str
    refresh_token: str
    session_started_at: float

    @classmethod
    def load(cls, value: str) -> StoredCredentials:
        return cls(**json.loads(value))

    def dump(self) -> str:
        return json.dumps(vars(self), separators=(",", ":"))


class ApiClient:
    def __init__(self, project: str, api_url: str | None = None) -> None:
        self.project = project
        self.api_url = (api_url or os.getenv("NUBOR_API_URL") or DEFAULT_API_URL).rstrip("/")
        parsed = urllib.parse.urlparse(self.api_url)
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise click.ClickException("the Nubor API endpoint must use HTTPS")
        self.issuer = (os.getenv("NUBOR_OIDC_ISSUER") or DEFAULT_ISSUER).rstrip("/")
        self.client_id = os.getenv("NUBOR_OIDC_CLIENT_ID") or DEFAULT_CLIENT_ID
        self.service = f"nubor:{parsed.netloc}"
        self.account = f"project:{project}"

    def _stored(self) -> StoredCredentials | None:
        try:
            value = keyring.get_password(self.service, self.account)
        except keyring.errors.KeyringError as exc:
            raise click.ClickException(
                "the operating-system credential store is unavailable"
            ) from exc
        if not value:
            return None
        try:
            return StoredCredentials.load(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            self.clear_credentials()
            return None

    def _save(self, credentials: StoredCredentials) -> None:
        try:
            keyring.set_password(self.service, self.account, credentials.dump())
        except keyring.errors.KeyringError as exc:
            raise click.ClickException(
                "the operating-system credential store is unavailable"
            ) from exc

    def clear_credentials(self) -> None:
        try:
            keyring.delete_password(self.service, self.account)
        except keyring.errors.PasswordDeleteError:
            pass
        except keyring.errors.KeyringError as exc:
            raise click.ClickException(
                "the operating-system credential store is unavailable"
            ) from exc

    @staticmethod
    def _json_request(
        url: str,
        *,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        form: bool = False,
    ) -> tuple[Any, dict[str, str], int]:
        body = None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if data is not None:
            if form:
                body = urllib.parse.urlencode(data).encode()
                request_headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(data).encode()
                request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as result:
                payload = result.read()
                parsed = json.loads(payload) if payload else None
                return parsed, dict(result.headers.items()), result.status
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                detail = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                detail = {}
            title = (
                detail.get("error_description")
                or detail.get("detail")
                or detail.get("title")
                or detail.get("error")
                or f"request failed ({exc.code})"
            )
            error = click.ClickException(str(title))
            error.exit_code = exc.code
            raise error from None
        except urllib.error.URLError as exc:
            raise click.ClickException(
                f"could not reach {urllib.parse.urlparse(url).netloc}"
            ) from exc

    def _discovery(self) -> dict[str, Any]:
        value, _, _ = self._json_request(f"{self.issuer}/.well-known/openid-configuration")
        return dict(value)

    def device_login(self) -> dict[str, Any]:
        discovery = self._discovery()
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()
        challenge = challenge.rstrip("=")
        device, _, _ = self._json_request(
            discovery["device_authorization_endpoint"],
            method="POST",
            form=True,
            data={
                "client_id": self.client_id,
                "scope": SCOPES,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        verification_url = device.get("verification_uri_complete") or device["verification_uri"]
        click.echo(f"Open {verification_url}")
        if device.get("user_code"):
            click.echo(f"Code: {device['user_code']}")
        webbrowser.open(verification_url)

        interval = max(1, int(device.get("interval", 5)))
        deadline = time.monotonic() + min(int(device.get("expires_in", 600)), 600)
        tokens: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            time.sleep(interval)
            try:
                tokens, _, _ = self._json_request(
                    discovery["token_endpoint"],
                    method="POST",
                    form=True,
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code": device["device_code"],
                        "client_id": self.client_id,
                        "code_verifier": verifier,
                    },
                )
                break
            except click.ClickException as exc:
                if exc.exit_code == 400 and "authorization_pending" in str(exc):
                    continue
                if exc.exit_code == 400 and "slow_down" in str(exc):
                    interval += 5
                    continue
                raise
        if not tokens:
            raise click.ClickException("the device login expired")
        return self._exchange(tokens, time.time())

    def _exchange(self, oidc_tokens: dict[str, Any], started_at: float) -> dict[str, Any]:
        identity, headers, _ = self._json_request(
            f"{self.api_url}/v1/auth/exchange",
            method="POST",
            data={"access_token": oidc_tokens["access_token"], "project": self.project},
        )
        token = headers.get("X-Subject-Token") or headers.get("x-subject-token")
        if not token:
            raise click.ClickException("the API did not return a project token")
        credentials = StoredCredentials(
            keystone_token=token,
            keystone_expires_at=identity["expires_at"],
            refresh_token=oidc_tokens.get("refresh_token", ""),
            session_started_at=started_at,
        )
        self._save(credentials)
        return identity

    def _refresh(self, credentials: StoredCredentials) -> StoredCredentials:
        if time.time() - credentials.session_started_at > MAX_SESSION_SECONDS:
            self.clear_credentials()
            raise click.ClickException("the 8-hour login session expired; run 'nubor auth login'")
        if not credentials.refresh_token:
            raise click.ClickException("run 'nubor auth login' to renew the session")
        discovery = self._discovery()
        oidc, _, _ = self._json_request(
            discovery["token_endpoint"],
            method="POST",
            form=True,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": credentials.refresh_token,
            },
        )
        if "refresh_token" not in oidc:
            oidc["refresh_token"] = credentials.refresh_token
        self._exchange(oidc, credentials.session_started_at)
        refreshed = self._stored()
        if refreshed is None:  # pragma: no cover - save followed by load
            raise click.ClickException("could not persist the renewed session")
        return refreshed

    def request(self, path: str, *, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
        credentials = self._stored()
        if credentials is None:
            raise click.ClickException("not logged in; run 'nubor auth login'")
        try:
            return self._json_request(
                f"{self.api_url}{path}",
                method=method,
                data=data,
                headers={"Authorization": f"Bearer {credentials.keystone_token}"},
            )[0]
        except click.ClickException as exc:
            if exc.exit_code != 401:
                raise
        credentials = self._refresh(credentials)
        return self._json_request(
            f"{self.api_url}{path}",
            method=method,
            data=data,
            headers={"Authorization": f"Bearer {credentials.keystone_token}"},
        )[0]

    def logout(self) -> None:
        credentials = self._stored()
        if credentials:
            try:
                self.request("/v1/auth/session", method="DELETE")
            finally:
                self.clear_credentials()


def _find(items: list[ApiResource], name_or_id: str, label: str) -> ApiResource | None:
    matches = [item for item in items if item.id == name_or_id or item.name == name_or_id]
    if len(matches) > 1:
        raise click.ClickException(f"multiple {label}s found matching '{name_or_id}'")
    return matches[0] if matches else None


class ComputeProxy:
    def __init__(self, client: ApiClient) -> None:
        self.client = client
        self._metadata_keys: dict[str, str] = {}

    def servers(self, **_: Any) -> list[ApiResource]:
        return [_resource(item) for item in self.client.request("/v1/instances")]

    def find_server(self, name_or_id: str, ignore_missing: bool = True) -> ApiResource | None:
        value = _find(self.servers(), name_or_id, "instance")
        if value is None and not ignore_missing:
            raise openstack.exceptions.NotFoundException()
        return value

    def get_server(self, server_id: str) -> ApiResource:
        return _resource(self.client.request(f"/v1/instances/{server_id}"))

    def flavors(self) -> list[ApiResource]:
        return [_resource(item) for item in self.client.request("/v1/flavors")]

    def find_flavor(self, name_or_id: str, ignore_missing: bool = True) -> ApiResource | None:
        value = _find(self.flavors(), name_or_id, "flavor")
        if value is None and not ignore_missing:
            raise openstack.exceptions.NotFoundException()
        return value

    def delete_server(self, server: ApiResource) -> None:
        self.client.request(f"/v1/instances/{server.id}", method="DELETE")

    def start_server(self, server: ApiResource) -> None:
        self.client.request(f"/v1/instances/{server.id}/actions/start", method="POST")

    def stop_server(self, server: ApiResource) -> None:
        self.client.request(f"/v1/instances/{server.id}/actions/stop", method="POST")

    def reboot_server(self, server: ApiResource, reboot_type: str) -> None:
        hard = "?hard=true" if reboot_type == "HARD" else ""
        self.client.request(f"/v1/instances/{server.id}/actions/reboot{hard}", method="POST")

    def wait_for_server(self, server: ApiResource, wait: int = 300) -> ApiResource:
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            server = self.get_server(server.id)
            if server.status == "ACTIVE":
                return server
            if server.status == "ERROR":
                raise openstack.exceptions.ResourceFailure("instance entered ERROR")
            time.sleep(2)
        raise openstack.exceptions.ResourceTimeout("instance did not become ACTIVE")

    def wait_for_delete(self, server: ApiResource, wait: int = 300) -> None:
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                self.get_server(server.id)
            except click.ClickException as exc:
                if exc.exit_code == 404:
                    return
                raise
            time.sleep(2)
        raise openstack.exceptions.ResourceTimeout("instance was not deleted")

    def set_server_metadata(self, server: ApiResource, **metadata: str) -> ApiResource:
        for local_id, value in metadata.items():
            user, expiry, public_key = value.split(":", 2)
            result = self.client.request(
                f"/v1/instances/{server.id}/ssh-keys",
                method="POST",
                data={
                    "user": user,
                    "public_key": public_key,
                    "ttl": max(30, int(expiry) - int(time.time())),
                },
            )
            self._metadata_keys[local_id] = result["id"]
        return server

    def delete_server_metadata(self, server: ApiResource, keys: list[str]) -> None:
        for local_id in keys:
            remote_id = self._metadata_keys.get(local_id, local_id)
            self.client.request(f"/v1/instances/{server.id}/ssh-keys/{remote_id}", method="DELETE")

    def create_volume_attachment(self, server: ApiResource, volume: ApiResource) -> Any:
        return self.client.request(f"/v1/instances/{server.id}/volumes/{volume.id}", method="POST")

    def delete_volume_attachment(self, server: ApiResource, volume: ApiResource) -> None:
        self.client.request(f"/v1/instances/{server.id}/volumes/{volume.id}", method="DELETE")


class ImageProxy:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def images(self, **_: Any) -> list[ApiResource]:
        return [_resource(item) for item in self.client.request("/v1/images")]

    def find_image(self, name_or_id: str, ignore_missing: bool = True) -> ApiResource | None:
        value = _find(self.images(), name_or_id, "image")
        if value is None and not ignore_missing:
            raise openstack.exceptions.NotFoundException()
        return value

    def delete_image(self, *_: Any, **__: Any) -> None:
        raise click.ClickException("image deletion requires private break-glass mode (--direct)")


class NetworkProxy:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def networks(self, **filters: Any) -> list[ApiResource]:
        values = [_resource(item) for item in self.client.request("/v1/networks")]
        return [
            item
            for item in values
            if all(getattr(item, key, None) == value for key, value in filters.items())
        ]

    def find_network(self, name_or_id: str, ignore_missing: bool = True) -> ApiResource | None:
        value = _find(self.networks(), name_or_id, "network")
        if value is None and not ignore_missing:
            raise openstack.exceptions.NotFoundException()
        return value


class BlockStorageProxy:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def volumes(self, **_: Any) -> list[ApiResource]:
        return [_resource(item) for item in self.client.request("/v1/volumes")]

    def find_volume(self, name_or_id: str, ignore_missing: bool = True) -> ApiResource | None:
        value = _find(self.volumes(), name_or_id, "volume")
        if value is None and not ignore_missing:
            raise openstack.exceptions.NotFoundException()
        return value

    def create_volume(self, **attrs: Any) -> ApiResource:
        return _resource(self.client.request("/v1/volumes", method="POST", data=attrs))

    def delete_volume(self, volume: ApiResource) -> None:
        self.client.request(f"/v1/volumes/{volume.id}", method="DELETE")


class ApiConnection:
    def __init__(self, project: str, api_url: str | None = None) -> None:
        self.client = ApiClient(project, api_url)
        self.compute = ComputeProxy(self.client)
        self.image = ImageProxy(self.client)
        self.network = NetworkProxy(self.client)
        self.block_storage = BlockStorageProxy(self.client)

    def create_instance(
        self,
        *,
        name: str,
        flavor: ApiResource,
        image: ApiResource,
        network: ApiResource,
        key_name: str | None,
        static_private: bool,
        static_external: bool,
        external_network: ApiResource | None,
    ) -> ApiResource:
        accelerator = (
            [{"type": "nvidia-rtx-3080", "count": 1}] if flavor.name == "gpu.k8s.node" else []
        )
        return _resource(
            self.client.request(
                "/v1/instances",
                method="POST",
                data={
                    "name": name,
                    "image_id": image.id,
                    "machine_type": flavor.name,
                    "network": {
                        "id": network.id,
                        "private_address": "static" if static_private else "ephemeral",
                        "external_address": "static" if static_external else "none",
                        "external_network_id": external_network.id if external_network else None,
                    },
                    "accelerators": accelerator,
                    "ssh_key_name": key_name,
                },
            )
        )

    @property
    def container_infrastructure_management(self) -> Any:
        raise click.ClickException("Magnum requires private break-glass mode (--direct)")
