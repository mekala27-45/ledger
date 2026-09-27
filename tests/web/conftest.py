"""The web parity tests run the site's TypeScript directly with node's type stripping."""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _node_strips_types() -> bool:
    node = shutil.which("node")
    if node is None:
        return False
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=False).stdout.strip()
    try:
        major, minor = (int(x) for x in version.lstrip("v").split(".")[:2])
    except ValueError:
        return False
    return (major, minor) >= (22, 6)


@pytest.fixture(scope="session", autouse=True)
def _require_node() -> None:
    if not _node_strips_types():
        pytest.skip("node 22.6 or later is needed to run the site's TypeScript")
