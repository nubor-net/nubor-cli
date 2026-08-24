"""kubeconfig generation for Magnum clusters.

Magnum signs a client certificate for whoever asks with a CSR, the same way
`openstack coe cluster config` does: the private key never leaves the machine,
only the CSR is sent. Certificates are embedded in the kubeconfig rather than
written alongside it, so a single file is the whole credential.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def new_csr() -> tuple[bytes, bytes]:
    """Return (private key PEM, CSR PEM) for a cluster admin.

    Magnum's CA maps the CN to the Kubernetes user and the O to its groups, so
    admin/system:masters is what makes the resulting cert able to do anything.
    RSA rather than ed25519: Magnum's signing path is the only consumer and it
    has never accepted anything else.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "admin"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "system:masters"),
                ]
            )
        )
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key_pem, csr.public_bytes(serialization.Encoding.PEM)


def default_path() -> Path:
    """The file kubectl would write to: the first entry of KUBECONFIG, else
    ~/.kube/config."""
    env = os.environ.get("KUBECONFIG")
    if env:
        first = env.split(os.pathsep)[0]
        if first:
            return Path(first).expanduser()
    return Path.home() / ".kube" / "config"


def _b64(pem: str | bytes | None) -> str | None:
    if not pem:
        return None
    if isinstance(pem, str):
        pem = pem.encode()
    return base64.b64encode(pem).decode()


def entries(
    context: str,
    server: str,
    ca_pem: str | None,
    client_cert_pem: str | None,
    client_key_pem: bytes | None,
) -> tuple[dict, dict, dict]:
    """Build the (cluster, user, context) stanzas for one Magnum cluster."""
    cluster: dict[str, Any] = {"server": server}
    if ca_pem:
        cluster["certificate-authority-data"] = _b64(ca_pem)
    else:
        # tls_disabled clusters have no CA to pin. Say so rather than leaving
        # kubectl to fail on an unverifiable https endpoint.
        cluster["insecure-skip-tls-verify"] = True

    user: dict[str, Any] = {}
    if client_cert_pem and client_key_pem:
        user["client-certificate-data"] = _b64(client_cert_pem)
        user["client-key-data"] = _b64(client_key_pem)

    return (
        {"name": context, "cluster": cluster},
        {"name": context, "user": user},
        {"name": context, "context": {"cluster": context, "user": context}},
    )


def merge(path: Path, cluster: dict, user: dict, context: dict) -> None:
    """Merge one cluster/user/context into an existing kubeconfig, replacing
    same-named entries and making the new context current. Anything else in the
    file - other clusters, preferences, unknown keys - is left as it was."""
    doc: dict[str, Any] = {}
    if path.exists():
        doc = yaml.safe_load(path.read_text()) or {}

    doc.setdefault("apiVersion", "v1")
    doc.setdefault("kind", "Config")
    for key, entry in (("clusters", cluster), ("users", user), ("contexts", context)):
        existing = [e for e in doc.get(key) or [] if e.get("name") != entry["name"]]
        doc[key] = existing + [entry]
    doc["current-context"] = context["name"]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, default_flow_style=False, sort_keys=False))
    path.chmod(0o600)
