# PyInstaller spec for the standalone nubor binary.
#
# The collect_all list below is load-bearing: openstacksdk resolves these
# packages at runtime through stevedore/dogpile plugin entry points, which
# static analysis cannot see. Removing any of them produces a binary that
# builds fine and fails at the first API call (for example, a missing
# dogpile.cache backend surfaces as "could not connect" on every command).

from PyInstaller.utils.hooks import collect_all

RUNTIME_MODULES = [
    "openstack",
    "keystoneauth1",
    "os_service_types",
    "dogpile",
    "stevedore",
    "keystoneclient",
]

datas, binaries, hiddenimports = [], [], []
for module in RUNTIME_MODULES:
    d, b, h = collect_all(module)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["src/nubor/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="nubor",
    console=True,
    upx=False,
)
