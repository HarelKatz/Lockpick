"""authorized_keys option prefixes must reach CredentialLink.key_options and survive.

The dedup key for a CredentialLink is (credential_id, host_id, relationship_type,
username) — it does NOT include key_options. So setting key_options only when the
link is first created leaves it NULL forever on any re-upload, and on every link
created before options were parsed. These tests pin the backfill arm that covers it.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

FIXTURES = Path(__file__).parent.parent / "fixtures"

# A genuinely parseable key, reused across uploads. It must fingerprint: the credential
# upsert matches on fingerprint, so an unparseable placeholder would create a second
# credential (and therefore a second link) instead of exercising the dedup path.
_KEY = (FIXTURES / "authorized_keys_real_key").read_text().strip()
_OPTIONS = 'command="/usr/local/bin/backup",no-pty'


def _create_op(client) -> str:
    r = client.post("/api/ops", json={"name": "KeyOptionsOp"})
    assert r.status_code == 201
    return r.json()["id"]


def _create_host(client, op_id: str, nickname: str = "web01") -> str:
    r = client.post(f"/api/ops/{op_id}/hosts", json={"nickname": nickname})
    assert r.status_code == 201
    return r.json()["id"]


def _upload_authorized_keys(client, op_id: str, host_id: str, content: bytes):
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": host_id, "username": "alice"},
        files={"file": ("authorized_keys", content, "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _links(client, op_id: str):
    resp = client.get(f"/api/ops/{op_id}/credential-links")
    assert resp.status_code == 200
    return resp.json()


def test_options_persisted_on_first_upload(client):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    _upload_authorized_keys(client, op_id, host_id, f"{_OPTIONS} {_KEY}\n".encode())

    links = _links(client, op_id)
    assert len(links) == 1
    assert links[0]["key_options"] == _OPTIONS


def test_options_backfilled_when_link_already_exists(client):
    """The fail-provable one: the link is created WITHOUT options, then re-uploaded WITH them.

    Remove the `elif existing_link.key_options is None` arm in upload_pipeline and this
    fails — the dedup skips the row and key_options stays None. A single-upload test
    passes either way, which is exactly how this class of bug ships green.
    """
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # 1st upload: same key, no option prefix → link created with key_options NULL.
    _upload_authorized_keys(client, op_id, host_id, f"{_KEY}\n".encode())
    links = _links(client, op_id)
    assert len(links) == 1
    assert links[0]["key_options"] is None

    # 2nd upload: same key + user + host, now carrying options → dedup hits, backfill runs.
    _upload_authorized_keys(client, op_id, host_id, f"{_OPTIONS} {_KEY}\n".encode())

    links = _links(client, op_id)
    assert len(links) == 1, "re-upload must not create a second link"
    assert links[0]["key_options"] == _OPTIONS


def test_recorded_options_are_not_overwritten_by_a_later_unrestricted_upload(client):
    """Backfill fills a gap; it must never erase recorded grant evidence."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    _upload_authorized_keys(client, op_id, host_id, f"{_OPTIONS} {_KEY}\n".encode())
    _upload_authorized_keys(client, op_id, host_id, f"{_KEY}\n".encode())

    links = _links(client, op_id)
    assert len(links) == 1
    assert links[0]["key_options"] == _OPTIONS


def test_key_options_is_not_client_settable(client):
    """Parser-set field: absent from Create/Update, so a PATCH can't forge grant evidence."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    _upload_authorized_keys(client, op_id, host_id, f"{_OPTIONS} {_KEY}\n".encode())
    link = _links(client, op_id)[0]

    resp = client.patch(
        f"/api/credential-links/{link['id']}",
        json={"key_options": "command=\"/bin/sh\""},
    )
    assert resp.status_code in (200, 422)
    assert _links(client, op_id)[0]["key_options"] == _OPTIONS


def test_export_import_round_trip_preserves_key_options(client):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    _upload_authorized_keys(client, op_id, host_id, f"{_OPTIONS} {_KEY}\n".encode())

    exported = client.get(f"/api/ops/{op_id}/export")
    assert exported.status_code == 200
    payload = exported.json()

    resp = client.post("/api/ops/import", json={"data": payload})
    assert resp.status_code == 201, resp.text

    links = _links(client, resp.json()["op_id"])
    assert len(links) == 1
    assert links[0]["key_options"] == _OPTIONS


def test_import_tolerates_exports_written_before_key_options_existed(client):
    """Backward compat: ExportCredentialLink.key_options needs its `= None` default.

    A bare Optional[str] is *required* in Pydantic v2, so every pre-existing export
    would 422 on import. Simulate one by deleting the key.
    """
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    _upload_authorized_keys(client, op_id, host_id, f"{_OPTIONS} {_KEY}\n".encode())

    payload = client.get(f"/api/ops/{op_id}/export").json()
    for link in payload["credential_links"]:
        del link["key_options"]
    payload = json.loads(json.dumps(payload))

    resp = client.post("/api/ops/import", json={"data": payload})
    assert resp.status_code == 201, resp.text
    links = _links(client, resp.json()["op_id"])
    assert len(links) == 1
    assert links[0]["key_options"] is None
