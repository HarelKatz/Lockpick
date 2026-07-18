"""authorized_keys `from=` CIDR/glob ACLs as standing rules (Architecture Rules #27/#28).

Unlike a literal `from="10.0.0.5"`, a CIDR or glob matches a SET — including hosts
that do not exist yet — so it is stored as a standing rule and re-applied whenever a
host appears. These tests cover: containment matching, the inbound direction (an ACL
grants access INTO the upload host), the broad-prefix cap, and retroactive matching
against a host auto-created by a later upload.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

FIXTURES = Path(__file__).parent.parent / "fixtures"

_KEY = (FIXTURES / "authorized_keys_real_key").read_text().strip()


def _create_op(client) -> str:
    r = client.post("/api/ops", json={"name": "AclRulesOp"})
    assert r.status_code == 201
    return r.json()["id"]


def _create_host(client, op_id: str, nickname: str, ip: str | None = None) -> str:
    r = client.post(f"/api/ops/{op_id}/hosts", json={"nickname": nickname})
    assert r.status_code == 201
    host_id = r.json()["id"]
    if ip:
        r2 = client.post(f"/api/hosts/{host_id}/ips", json={"ip_address": ip})
        assert r2.status_code == 201, r2.text
    return host_id


def _upload_acl(client, op_id: str, host_id: str, from_value: str):
    content = f'from="{from_value}" {_KEY}\n'.encode()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": host_id, "username": "alice"},
        files={"file": ("authorized_keys", content, "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _edges(client, op_id: str, src_id: str, dst_id: str):
    graph = client.get(f"/api/ops/{op_id}/graph")
    assert graph.status_code == 200
    return [
        e for e in graph.json()["edges"]
        if e["src_host_id"] == src_id and e["dst_host_id"] == dst_id
    ]


def test_cidr_acl_matches_by_containment(client):
    """fnmatch can never match an IP against a prefix — this needs ip_network."""
    op_id = _create_op(client)
    target = _create_host(client, op_id, "target", "10.9.9.9")
    inside = _create_host(client, op_id, "inside", "10.0.0.7")
    outside = _create_host(client, op_id, "outside", "192.168.1.4")

    _upload_acl(client, op_id, target, "10.0.0.0/24")

    assert len(_edges(client, op_id, inside, target)) == 1
    assert _edges(client, op_id, outside, target) == []


def test_acl_edge_direction_is_inbound(client):
    """The ACL lives on the destination: matching hosts point INTO the upload host."""
    op_id = _create_op(client)
    target = _create_host(client, op_id, "target", "10.9.9.9")
    inside = _create_host(client, op_id, "inside", "10.0.0.7")

    _upload_acl(client, op_id, target, "10.0.0.0/24")

    assert len(_edges(client, op_id, inside, target)) == 1
    # …and emphatically NOT the reverse, which is the ssh_config orientation.
    assert _edges(client, op_id, target, inside) == []


def test_glob_acl_matches_hostnames(client):
    op_id = _create_op(client)
    target = _create_host(client, op_id, "target", "10.9.9.9")
    match = _create_host(client, op_id, "web.corp.net")
    other = _create_host(client, op_id, "db.other.net")

    _upload_acl(client, op_id, target, "*.corp.net")

    assert len(_edges(client, op_id, match, target)) == 1
    assert _edges(client, op_id, other, target) == []


def test_negation_excludes_a_host_the_glob_would_match(client):
    op_id = _create_op(client)
    target = _create_host(client, op_id, "target", "10.9.9.9")
    allowed = _create_host(client, op_id, "web.corp.net")
    denied = _create_host(client, op_id, "jump.corp.net")

    _upload_acl(client, op_id, target, "*.corp.net,!jump.corp.net")

    assert len(_edges(client, op_id, allowed, target)) == 1
    assert _edges(client, op_id, denied, target) == []


def test_broad_cidr_is_capped_and_warns(client, monkeypatch):
    """A prefix matching most of the op emits no edges — it would be a hairball."""
    from config import settings

    monkeypatch.setattr(settings, "standing_rule_max_matches", 2)
    op_id = _create_op(client)
    target = _create_host(client, op_id, "target", "192.168.50.1")
    members = [
        _create_host(client, op_id, f"h{i}", f"10.0.0.{i}") for i in range(1, 5)
    ]

    body = _upload_acl(client, op_id, target, "10.0.0.0/8")

    warnings = body["summary"]["warnings"]
    assert any("edges suppressed" in w for w in warnings), warnings
    for m in members:
        assert _edges(client, op_id, m, target) == [], "capped rule must emit no edges"


def test_rule_applies_retroactively_to_a_host_created_by_a_later_upload(client):
    """The load-bearing case: the ACL is ingested BEFORE the host exists.

    The host is then auto-created by a later upload — the path that previously never
    triggered rule matching at all (Architecture Rule #28).
    """
    op_id = _create_op(client)
    target = _create_host(client, op_id, "target", "10.9.9.9")
    origin = _create_host(client, op_id, "origin", "172.16.0.1")

    # ACL first, naming a range no host occupies yet.
    _upload_acl(client, op_id, target, "10.0.0.0/24")
    assert len(client.get(f"/api/ops/{op_id}/hosts").json()) == 2

    # A later bash_history upload auto-creates 10.0.0.7 via resolve_ip.
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "bash_history", "host_id": origin, "username": "alice"},
        files={"file": (".bash_history", b"ssh alice@10.0.0.7\n", "text/plain")},
    )
    assert resp.status_code == 200, resp.text

    hosts = client.get(f"/api/ops/{op_id}/hosts").json()
    new_host = next(
        h for h in hosts
        if any(ip["ip_address"] == "10.0.0.7" for ip in h.get("ips", []))
    )

    edges = _edges(client, op_id, new_host["id"], target)
    assert len(edges) == 1, "the ACL must reach a host discovered after it was ingested"
    assert edges[0]["confidence"] == "indicator"
