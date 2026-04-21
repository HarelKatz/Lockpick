"""API tests for sudo rules endpoints."""
import pytest
from datetime import datetime, timezone

from models import SudoRule


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


@pytest.fixture
def host(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "web01"})
    return resp.json()


def test_list_empty(client, host):
    """A new host has no sudo rules."""
    resp = client.get(f"/api/hosts/{host['id']}/sudo-rules")
    assert resp.status_code == 200
    assert resp.json() == []


def test_delete_sudo_rule(client, db_session, op, host):
    """Manually insert a SudoRule via DB, DELETE it, verify gone."""
    rule = SudoRule(
        host_id=host["id"],
        op_id=op["id"],
        subject="alice",
        subject_type="user",
        run_as="root",
        commands="/bin/bash",
        nopasswd=True,
        raw_line="alice ALL=(root) NOPASSWD: /bin/bash",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(rule)
    db_session.commit()

    # Verify it shows up in the list
    list_resp = client.get(f"/api/hosts/{host['id']}/sudo-rules")
    assert list_resp.status_code == 200
    rules = list_resp.json()
    assert len(rules) == 1
    rule_id = rules[0]["id"]
    assert rules[0]["subject"] == "alice"
    assert rules[0]["nopasswd"] is True

    # Delete it
    del_resp = client.delete(f"/api/hosts/{host['id']}/sudo-rules/{rule_id}")
    assert del_resp.status_code == 204

    # Verify it's gone
    list_resp2 = client.get(f"/api/hosts/{host['id']}/sudo-rules")
    assert list_resp2.json() == []


def test_404_on_invalid_host(client):
    """GET on nonexistent host returns 404."""
    resp = client.get("/api/hosts/nonexistent-host-id/sudo-rules")
    assert resp.status_code == 404


def test_delete_404_on_invalid_rule(client, host):
    """DELETE on nonexistent rule returns 404."""
    resp = client.delete(f"/api/hosts/{host['id']}/sudo-rules/nonexistent-rule-id")
    assert resp.status_code == 404


def test_delete_404_wrong_host(client, db_session, op, host):
    """DELETE on a rule belonging to a different host returns 404."""
    # Create a second host
    resp2 = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "db01"})
    other_host = resp2.json()

    # Add a rule to the first host
    rule = SudoRule(
        host_id=host["id"],
        op_id=op["id"],
        subject="bob",
        subject_type="user",
        run_as="root",
        commands="/usr/bin/vim",
        nopasswd=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(rule)
    db_session.commit()

    # Try to delete via the other host's endpoint
    list_resp = client.get(f"/api/hosts/{host['id']}/sudo-rules")
    rule_id = list_resp.json()[0]["id"]

    del_resp = client.delete(f"/api/hosts/{other_host['id']}/sudo-rules/{rule_id}")
    assert del_resp.status_code == 404
