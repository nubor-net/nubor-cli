# PyInstaller spec for the standalone nubor binary.
#
# The lists below are load-bearing. openstacksdk resolves plugins at runtime
# through stevedore and dogpile entry points, which static analysis cannot see.
# Dropping an entry produces a binary that builds and passes --help, then fails
# on the first API call with a message that looks like a connection problem.

from PyInstaller.utils.hooks import collect_all, copy_metadata

# Collected wholesale: data files, submodules and dynamic libraries.
RUNTIME_MODULES = [
    "openstack",
    "keystoneauth1",
    "os_service_types",
    "dogpile",
    "stevedore",
    # keyring finds its OS backend through entry points at login time.
    "keyring",
]

# collect_all() looks metadata up by distribution name, which differs from the
# import name for these two, so it silently skips them. openstacksdk reads its
# own version from metadata at runtime, so collect them explicitly.
# (python-keystoneclient is deliberately absent: openstacksdk does not depend on
# it, it is not installed, and collecting it contributed zero files.)
METADATA_DISTRIBUTIONS = [
    "openstacksdk",
    "dogpile.cache",
    "keyring",
]

datas, binaries, hiddenimports = [], [], []
for module in RUNTIME_MODULES:
    d, b, h = collect_all(module)
    datas += d
    binaries += b
    hiddenimports += h

for distribution in METADATA_DISTRIBUTIONS:
    datas += copy_metadata(distribution)

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
