"""Offline tests: render every router's config and check key lines.

These run without Docker, so they catch template and data mistakes early.
"""
import ipaddress

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from conftest import ROOT, load_host_vars

HOSTS = load_host_vars()
ENV = Environment(
    loader=FileSystemLoader(str(ROOT / "templates")),
    undefined=StrictUndefined,
    trim_blocks=True,
)


def render(host):
    return ENV.get_template("frr.conf.j2").render(inventory_hostname=host, **HOSTS[host])


@pytest.mark.parametrize("host", HOSTS)
def test_config_renders(host):
    config = render(host)
    assert f"hostname {host}" in config
    assert config.rstrip().endswith("end")


@pytest.mark.parametrize("host", HOSTS)
def test_every_interface_configured(host):
    config = render(host)
    for intf in HOSTS[host]["interfaces"]:
        assert f"interface {intf['name']}" in config
        assert f"ip address {intf['ip']}" in config


@pytest.mark.parametrize("host", [h for h in HOSTS if "bgp" in HOSTS[h]])
def test_bgp_neighbors_rendered(host):
    config = render(host)
    for n in HOSTS[host]["bgp"]["neighbors"]:
        assert f"neighbor {n['ip']} remote-as {n['remote_as']}" in config


def test_point_to_point_links_match():
    """Both ends of each link must be in the same /30 subnet."""
    subnets = {}
    for host, data in HOSTS.items():
        for intf in data["interfaces"]:
            net = ipaddress.ip_interface(intf["ip"]).network
            subnets.setdefault(net, []).append(host)
    for net, members in subnets.items():
        assert len(members) == 2, f"{net} is used by {members}"


def test_bgp_neighbors_are_symmetric():
    """If A peers with B's address, B must peer back with A."""
    addresses = {}
    for host, data in HOSTS.items():
        addresses[data["loopback"].split("/")[0]] = host
        for intf in data["interfaces"]:
            addresses[intf["ip"].split("/")[0]] = host
    for host, data in HOSTS.items():
        for n in data.get("bgp", {}).get("neighbors", []):
            peer = addresses[n["ip"]]
            peer_neighbors = {x["ip"] for x in HOSTS[peer]["bgp"]["neighbors"]}
            my_addresses = {ip for ip, h in addresses.items() if h == host}
            assert peer_neighbors & my_addresses, f"{peer} does not peer back with {host}"
