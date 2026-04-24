"""Tests for WebSocket broadcast events.

Two layers:
1. ConnectionManager unit tests — connect/disconnect/broadcast behavior.
2. Endpoint integration tests — verify broadcast_sync is called from each
   mutation endpoint that was wired up in the broadcast commit.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── ConnectionManager unit tests ────────────────────────────────────────────

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from ws_manager import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


def _mock_ws():
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_registers_socket(manager):
    ws = _mock_ws()
    await manager.connect(ws, "op-1")
    assert ws in manager._connections["op-1"]


@pytest.mark.asyncio
async def test_disconnect_removes_socket(manager):
    ws = _mock_ws()
    await manager.connect(ws, "op-1")
    manager.disconnect(ws, "op-1")
    assert ws not in manager._connections.get("op-1", [])


@pytest.mark.asyncio
async def test_disconnect_unknown_socket_is_noop(manager):
    ws = _mock_ws()
    manager.disconnect(ws, "op-nonexistent")  # must not raise


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_connected(manager):
    ws1, ws2 = _mock_ws(), _mock_ws()
    await manager.connect(ws1, "op-1")
    await manager.connect(ws2, "op-1")
    event = {"type": "update", "entity_type": "host"}
    await manager.broadcast("op-1", event)
    ws1.send_json.assert_awaited_once_with(event)
    ws2.send_json.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_broadcast_different_op_not_sent(manager):
    ws1, ws2 = _mock_ws(), _mock_ws()
    await manager.connect(ws1, "op-1")
    await manager.connect(ws2, "op-2")
    await manager.broadcast("op-1", {"type": "update"})
    ws1.send_json.assert_awaited_once()
    ws2.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_removes_dead_sockets(manager):
    ws_good, ws_dead = _mock_ws(), _mock_ws()
    ws_dead.send_json.side_effect = RuntimeError("connection closed")
    await manager.connect(ws_good, "op-1")
    await manager.connect(ws_dead, "op-1")
    await manager.broadcast("op-1", {"type": "update"})
    assert ws_dead not in manager._connections.get("op-1", [])
    assert ws_good in manager._connections["op-1"]


@pytest.mark.asyncio
async def test_broadcast_empty_op_is_noop(manager):
    await manager.broadcast("op-nobody", {"type": "update"})  # must not raise


# ─── Endpoint integration: broadcast_sync is called ──────────────────────────


@pytest.fixture
def op(client):
    return client.post("/api/ops", json={"name": "BroadcastOp"}).json()


@pytest.fixture
def host(client, op):
    return client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "box"}).json()


@pytest.fixture
def cred(client, op):
    return client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "s3cr3t"},
    ).json()


@pytest.fixture
def connection(client, op, host):
    return client.post(
        f"/api/ops/{op['id']}/connections",
        json={"src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "connection_type": "ssh",
              "direction_context": "from_src_logs", "source_file": "test.log"},
    ).json()


def _patch_broadcast(module: str):
    return patch(f"{module}.broadcast_sync")


# hosts router

def test_add_host_ip_broadcasts(client, host):
    with _patch_broadcast("routers.hosts") as mock_bc:
        resp = client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "10.0.0.5"})
    assert resp.status_code == 201
    mock_bc.assert_called_once()
    args = mock_bc.call_args[0]
    assert args[0] == host["op_id"]
    assert args[1]["entity_type"] == "host"


def test_delete_host_ip_broadcasts(client, host):
    ip_id = client.post(
        f"/api/hosts/{host['id']}/ips", json={"ip_address": "10.0.0.6"}
    ).json()["id"]
    with _patch_broadcast("routers.hosts") as mock_bc:
        resp = client.delete(f"/api/hosts/{host['id']}/ips/{ip_id}")
    assert resp.status_code == 204
    mock_bc.assert_called_once()


def test_create_host_user_broadcasts(client, host):
    with _patch_broadcast("routers.hosts") as mock_bc:
        resp = client.post(f"/api/hosts/{host['id']}/users", json={"username": "alice"})
    assert resp.status_code == 201
    mock_bc.assert_called_once()


def test_delete_host_user_broadcasts(client, host):
    user_id = client.post(
        f"/api/hosts/{host['id']}/users", json={"username": "bob"}
    ).json()["id"]
    with _patch_broadcast("routers.hosts") as mock_bc:
        resp = client.delete(f"/api/hosts/{host['id']}/users/{user_id}")
    assert resp.status_code == 204
    mock_bc.assert_called_once()


# credentials router

def test_update_credential_broadcasts(client, cred):
    with _patch_broadcast("routers.credentials") as mock_bc:
        resp = client.patch(f"/api/credentials/{cred['id']}", json={"name": "renamed"})
    assert resp.status_code == 200
    mock_bc.assert_called_once()
    assert mock_bc.call_args[0][1]["entity_type"] == "credential"


def test_create_credential_link_broadcasts(client, op, host, cred):
    with _patch_broadcast("routers.credentials") as mock_bc:
        resp = client.post(
            "/api/credential-links",
            json={"credential_id": cred["id"], "host_id": host["id"],
                  "username": "root", "relationship_type": "found_on_disk"},
        )
    assert resp.status_code == 201
    mock_bc.assert_called_once()


def test_update_credential_link_broadcasts(client, op, host, cred):
    link_id = client.post(
        "/api/credential-links",
        json={"credential_id": cred["id"], "host_id": host["id"],
              "username": "root", "relationship_type": "found_on_disk"},
    ).json()["id"]
    with _patch_broadcast("routers.credentials") as mock_bc:
        resp = client.patch(f"/api/credential-links/{link_id}", json={"username": "www-data"})
    assert resp.status_code == 200
    mock_bc.assert_called_once()


def test_delete_credential_link_broadcasts(client, op, host, cred):
    link_id = client.post(
        "/api/credential-links",
        json={"credential_id": cred["id"], "host_id": host["id"],
              "username": "root", "relationship_type": "found_on_disk"},
    ).json()["id"]
    with _patch_broadcast("routers.credentials") as mock_bc:
        resp = client.delete(f"/api/credential-links/{link_id}")
    assert resp.status_code == 204
    mock_bc.assert_called_once()


# connections router

def test_update_connection_broadcasts(client, connection):
    with _patch_broadcast("routers.connections") as mock_bc:
        resp = client.patch(
            f"/api/connections/{connection['id']}", json={"src_user": "root"}
        )
    assert resp.status_code == 200
    mock_bc.assert_called_once()
    assert mock_bc.call_args[0][1]["entity_type"] == "connection"


# ─── Priority 13: Missing broadcast coverage ──────────────────────────────────

# hosts router — create, update, delete

def test_create_host_broadcasts(client, op):
    with _patch_broadcast("routers.hosts") as mock_bc:
        resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "newhost"})
    assert resp.status_code == 201
    mock_bc.assert_called_once()
    assert mock_bc.call_args[0][1]["entity_type"] == "host"


def test_update_host_broadcasts(client, host):
    with _patch_broadcast("routers.hosts") as mock_bc:
        resp = client.patch(f"/api/hosts/{host['id']}", json={"comment": "updated"})
    assert resp.status_code == 200
    mock_bc.assert_called_once()
    assert mock_bc.call_args[0][1]["entity_type"] == "host"


def test_delete_host_broadcasts(client, host):
    with _patch_broadcast("routers.hosts") as mock_bc:
        resp = client.delete(f"/api/hosts/{host['id']}")
    assert resp.status_code == 204
    mock_bc.assert_called_once()


# credentials router — create, delete

def test_create_credential_broadcasts(client, op):
    with _patch_broadcast("routers.credentials") as mock_bc:
        resp = client.post(
            f"/api/ops/{op['id']}/credentials",
            json={"cred_type": "password", "value": "newpass"},
        )
    assert resp.status_code == 201
    mock_bc.assert_called_once()
    assert mock_bc.call_args[0][1]["entity_type"] == "credential"


def test_delete_credential_broadcasts(client, cred):
    with _patch_broadcast("routers.credentials") as mock_bc:
        resp = client.delete(f"/api/credentials/{cred['id']}")
    assert resp.status_code == 204
    mock_bc.assert_called_once()


# connections router — create, delete

def test_create_connection_broadcasts(client, op):
    with _patch_broadcast("routers.connections") as mock_bc:
        resp = client.post(
            f"/api/ops/{op['id']}/connections",
            json={
                "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2",
                "direction_context": "from_src_logs", "source_file": "test.log",
            },
        )
    assert resp.status_code == 201
    mock_bc.assert_called_once()
    assert mock_bc.call_args[0][1]["entity_type"] == "connection"


def test_delete_connection_broadcasts(client, connection):
    with _patch_broadcast("routers.connections") as mock_bc:
        resp = client.delete(f"/api/connections/{connection['id']}")
    assert resp.status_code == 204
    mock_bc.assert_called_once()


# upload router — broadcasts on file upload

def test_upload_file_broadcasts(client, op, host, tmp_path):
    with _patch_broadcast("routers.upload") as mock_bc:
        resp = client.post(
            f"/api/ops/{op['id']}/upload",
            data={"file_type": "bash_history", "host_id": host["id"]},
            files={"file": (".bash_history", b"ssh root@10.0.0.1\n", "text/plain")},
        )
    assert resp.status_code == 200
    mock_bc.assert_called_once()
    assert mock_bc.call_args[0][1]["entity_type"] == "host"
