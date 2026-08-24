from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest import mock

import yaml
from click.testing import CliRunner
from cryptography import x509

from nubor.cli import main
from nubor.core import kube


def test_new_csr_is_cluster_admin():
    key_pem, csr_pem = kube.new_csr()
    csr = x509.load_pem_x509_csr(csr_pem)
    assert csr.is_signature_valid
    assert csr.subject.rfc4514_string() == "O=system:masters,CN=admin"
    assert b"PRIVATE KEY" in key_pem


def test_merge_replaces_same_name_and_keeps_the_rest(tmp_path):
    path = tmp_path / "config"
    path.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "clusters": [{"name": "other", "cluster": {"server": "https://other"}}],
                "users": [{"name": "other", "user": {}}],
                "contexts": [{"name": "other", "context": {}}],
                "preferences": {"colors": True},
                "current-context": "other",
            }
        )
    )
    for server in ("https://one", "https://two"):
        kube.merge(path, *kube.entries("prod", server, "CA", "CERT", b"KEY"))

    doc = yaml.safe_load(path.read_text())
    assert [c["name"] for c in doc["clusters"]] == ["other", "prod"]
    prod = next(c for c in doc["clusters"] if c["name"] == "prod")
    assert prod["cluster"]["server"] == "https://two"
    assert base64.b64decode(prod["cluster"]["certificate-authority-data"]) == b"CA"
    assert doc["preferences"] == {"colors": True}
    assert doc["current-context"] == "prod"


def test_entries_without_tls_skips_verification():
    cluster, user, _ = kube.entries("prod", "http://api", None, None, None)
    assert cluster["cluster"]["insecure-skip-tls-verify"] is True
    assert user["user"] == {}


def test_get_credentials_signs_a_csr_and_writes_the_file(fake_conn, tmp_path):
    magnum = fake_conn.container_infrastructure_management
    magnum.find_cluster.return_value = SimpleNamespace(
        name="prod",
        uuid="c-1",
        status="CREATE_COMPLETE",
        api_address="https://api.example:6443",
        tls_disabled=False,
    )
    magnum.get_cluster_certificate.return_value = SimpleNamespace(pem="CA-PEM")
    magnum.create_cluster_certificate.return_value = SimpleNamespace(pem="CLIENT-PEM")
    path = tmp_path / "kubeconfig"

    result = CliRunner().invoke(
        main,
        ["container", "clusters", "get-credentials", "prod", "--kubeconfig", str(path)],
    )
    assert result.exit_code == 0, result.output

    sent = magnum.create_cluster_certificate.call_args.kwargs
    assert sent["cluster_uuid"] == "c-1"
    assert x509.load_pem_x509_csr(sent["csr"].encode()).is_signature_valid

    doc = yaml.safe_load(path.read_text())
    assert doc["current-context"] == "prod"
    assert doc["clusters"][0]["cluster"]["server"] == "https://api.example:6443"
    assert base64.b64decode(doc["users"][0]["user"]["client-certificate-data"]) == b"CLIENT-PEM"


def test_get_credentials_refuses_a_cluster_with_no_api_address(fake_conn, tmp_path):
    fake_conn.container_infrastructure_management.find_cluster.return_value = SimpleNamespace(
        name="prod", uuid="c-1", status="CREATE_IN_PROGRESS", api_address=None, tls_disabled=False
    )
    path = tmp_path / "kubeconfig"
    result = CliRunner().invoke(
        main,
        ["container", "clusters", "get-credentials", "prod", "--kubeconfig", str(path)],
    )
    assert result.exit_code == 1
    assert "no API address" in result.output
    assert not path.exists()


def test_default_path_follows_kubeconfig_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KUBECONFIG", f"{tmp_path / 'first'}{__import__('os').pathsep}/other")
    assert kube.default_path() == tmp_path / "first"
    monkeypatch.delenv("KUBECONFIG")
    assert kube.default_path().name == "config"


def test_merge_makes_the_file_private(tmp_path):
    path = tmp_path / "config"
    with mock.patch.object(kube.Path, "chmod") as chmod:
        kube.merge(path, *kube.entries("prod", "https://api", "CA", "CERT", b"KEY"))
    chmod.assert_called_once_with(0o600)
