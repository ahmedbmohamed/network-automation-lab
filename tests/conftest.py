"""Shared helpers: read the source of truth and run commands in the lab."""
import json
import subprocess
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
LAB_NAME = "netlab"


def load_host_vars():
    """Return {hostname: host_vars} for every router in the inventory."""
    inventory = yaml.safe_load((ROOT / "inventory" / "hosts.yml").read_text())
    hosts = []
    for group in inventory["all"]["children"].values():
        hosts.extend(group["hosts"].keys())
    return {
        h: yaml.safe_load((ROOT / "inventory" / "host_vars" / f"{h}.yml").read_text())
        for h in hosts
    }


def run(host, command):
    """Run a shell command inside a router container and return stdout."""
    result = subprocess.run(
        ["docker", "exec", f"clab-{LAB_NAME}-{host}", "sh", "-c", command],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


def vtysh_json(host, command):
    """Run a vtysh show command with JSON output and parse it."""
    result = run(host, f'vtysh -c "{command} json"')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "{}")


def wait_until(check, timeout=120, interval=3):
    """Retry check() until it returns (truthy, detail) or the timeout expires."""
    deadline = time.time() + timeout
    ok, detail = check()
    while not ok and time.time() < deadline:
        time.sleep(interval)
        ok, detail = check()
    return ok, detail


@pytest.fixture(scope="session")
def host_vars():
    return load_host_vars()
