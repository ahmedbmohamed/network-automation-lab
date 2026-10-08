"""Automated checks of the running lab, derived from the source of truth.

Every expectation (OSPF neighbours, BGP sessions, reachable prefixes) is
computed from inventory/host_vars, so changing the design changes the tests.
"""
import pytest

from conftest import load_host_vars, run, vtysh_json, wait_until

HOSTS = load_host_vars()
OSPF_ROUTERS = [h for h, v in HOSTS.items() if "ospf" in v]
BGP_ROUTERS = [h for h, v in HOSTS.items() if "bgp" in v]
CUSTOMERS = [h for h, v in HOSTS.items() if v.get("bgp", {}).get("networks")]


def expected_ospf_neighbors(host):
    return sum(1 for i in HOSTS[host]["interfaces"] if i.get("ospf"))


@pytest.mark.parametrize("host", OSPF_ROUTERS)
def test_ospf_neighbors_full(host):
    """Every OSPF-enabled link has a neighbour in Full state."""
    expected = expected_ospf_neighbors(host)

    def check():
        data = vtysh_json(host, "show ip ospf neighbor")
        full = [
            n
            for entries in data.get("neighbors", {}).values()
            for n in entries
            if "Full" in str(n.get("nbrState", n.get("state", "")))
        ]
        return len(full) == expected, f"{len(full)}/{expected} Full neighbours"

    ok, detail = wait_until(check)
    assert ok, f"{host}: {detail}"


@pytest.mark.parametrize("host", BGP_ROUTERS)
def test_bgp_sessions_established(host):
    """Every BGP neighbour defined in the source of truth is Established."""
    expected = {n["ip"] for n in HOSTS[host]["bgp"]["neighbors"]}

    def check():
        data = vtysh_json(host, "show bgp summary")
        peers = data.get("ipv4Unicast", {}).get("peers", {})
        up = {ip for ip, p in peers.items() if p.get("state") == "Established"}
        return up == expected, f"established={sorted(up)} expected={sorted(expected)}"

    ok, detail = wait_until(check)
    assert ok, f"{host}: {detail}"


@pytest.mark.parametrize("src", CUSTOMERS)
def test_customer_routes_learned(src):
    """Each customer learns the other customers' prefixes through the provider."""
    others = [
        net
        for h in CUSTOMERS
        if h != src
        for net in HOSTS[h]["bgp"]["networks"]
    ]

    def check():
        routes = vtysh_json(src, "show ip route bgp")
        missing = [net for net in others if net not in routes]
        return not missing, f"missing routes: {missing}"

    ok, detail = wait_until(check)
    assert ok, f"{src}: {detail}"


@pytest.mark.parametrize("src", CUSTOMERS)
def test_customer_to_customer_ping(src):
    """End-to-end data plane: ping between customer LANs across the backbone."""
    source_ip = HOSTS[src]["loopback"].split("/")[0]
    targets = [
        HOSTS[h]["loopback"].split("/")[0] for h in CUSTOMERS if h != src
    ]
    for target in targets:

        def check():
            result = run(src, f"ping -c 2 -W 1 -I {source_ip} {target}")
            return result.returncode == 0, result.stdout[-200:]

        ok, detail = wait_until(check, timeout=60)
        assert ok, f"{src} -> {target} failed: {detail}"
