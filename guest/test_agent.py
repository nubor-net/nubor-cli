#!/usr/bin/env python3
"""Self-check for nubor-ssh-agent: python guest/test_agent.py

The agent runs as root and writes authorized_keys, so the parser is the part
that must not be wrong. Everything here is stdlib and has no dependency on the
CLI - pwd is stubbed so this runs on Windows too, and it stays runnable from
inside a guest where nubor itself is not installed.

The CLI/agent metadata format contract is covered in tests/test_ssh.py instead,
where the CLI is importable.
"""

import importlib.machinery
import importlib.util
import os
import pathlib
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).parent
HOMES = {}


class FakePasswd:
    def __init__(self, home):
        self.pw_dir, self.pw_uid, self.pw_gid = home, 0, 0


def getpwnam(name):
    if name not in ("ubuntu", "root"):
        raise KeyError(name)
    return FakePasswd(HOMES.setdefault(name, tempfile.mkdtemp()))


def load_agent():
    stub = types.ModuleType("pwd")
    stub.getpwnam = getpwnam
    sys.modules["pwd"] = stub
    loader = importlib.machinery.SourceFileLoader("nubor_ssh_agent", str(HERE / "nubor-ssh-agent"))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("nubor_ssh_agent", loader)
    )
    loader.exec_module(module)
    if os.name == "nt":  # no ownership/mode to set on Windows
        os.chown = lambda *args, **kwargs: None
        os.chmod = lambda *args, **kwargs: None
    return module


def main():
    agent = load_agent()
    now = 1000
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAKEKEYFAKEKEYFAKEKEYFAKEKEYFAKEKEYFA"

    assert agent.parse_entries({"nubor_ssh_a": f"ubuntu:2000:{key}"}, now) == {"ubuntu": [key]}

    rejected = [
        (f"ubuntu:500:{key}", "expired key"),
        (f"ubuntu:notanumber:{key}", "non-numeric expiry"),
        (f"nosuchuser:2000:{key}", "unknown local user"),
        (f"ubuntu:2000:{key}\nroot:x", "newline injects a second authorized_keys line"),
        ('ubuntu:2000:command="rm -rf /" ' + key, "forced-command options prefix"),
        ("ubuntu:2000:not-a-key AAAA", "unsupported key type"),
        ("ubuntu:2000", "missing field"),
    ]
    for value, why in rejected:
        assert agent.parse_entries({"nubor_ssh_x": value}, now) == {}, f"accepted {why}"

    # Metadata that is not ours is left alone, and a trailing comment cannot
    # smuggle anything: only type + blob are written out.
    assert agent.parse_entries({"other": f"ubuntu:2000:{key}"}, now) == {}
    assert agent.parse_entries({"nubor_ssh_a": f"ubuntu:2000:{key} comment"}, now) == {
        "ubuntu": [key]
    }

    home = getpwnam("ubuntu").pw_dir
    os.makedirs(os.path.join(home, ".ssh"), exist_ok=True)
    authorized = pathlib.Path(home, ".ssh", "authorized_keys")
    authorized.write_text("ssh-rsa USERSOWNKEY me\n")

    agent.write_authorized_keys("ubuntu", [key])
    text = authorized.read_text()
    assert "USERSOWNKEY" in text and key in text and agent.BEGIN_MARK in text

    agent.write_authorized_keys("ubuntu", [])  # what expiry does on the next pass
    text = authorized.read_text()
    assert "USERSOWNKEY" in text and key not in text and "nubor" not in text, text
    assert agent.write_authorized_keys("ubuntu", []) is False, "should be idempotent"

    print(f"ok: {len(rejected)} rejections, block add/remove/idempotent")


if __name__ == "__main__":
    main()
