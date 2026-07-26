"""Upload-pipeline handling of SystemInfoData (Architecture Rule #29)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _op(client) -> str:
    return client.post("/api/ops", json={"name": "TestOp"}).json()["id"]


def _host(client, op_id: str, nickname: str = "web01") -> str:
    return client.post(f"/api/ops/{op_id}/hosts", json={"nickname": nickname}).json()["id"]


def _upload(client, op_id: str, host_id: str, file_type: str, path: Path):
    return client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": file_type, "host_id": host_id},
        files={"file": (path.name, path.read_bytes(), "text/plain")},
    )


def test_os_release_upload_fills_the_source_host_os_version(client):
    op_id = _op(client)
    host_id = _host(client, op_id)

    resp = _upload(client, op_id, host_id, "os_release", FIXTURES / "os_release" / "os-release")
    assert resp.status_code == 200

    host = client.get(f"/api/hosts/{host_id}").json()
    assert host["os_version"] == "Ubuntu 22.04.3 LTS"
    assert host["kernel_version"] is None


def test_uname_upload_fills_the_source_host_kernel_version(client):
    op_id = _op(client)
    host_id = _host(client, op_id)

    resp = _upload(client, op_id, host_id, "uname_output", FIXTURES / "uname_output" / "uname-a.out")
    assert resp.status_code == 200

    host = client.get(f"/api/hosts/{host_id}").json()
    assert host["kernel_version"] == "5.15.0-88-generic"


def test_the_two_artifacts_compose_into_one_host(client):
    """os-release knows the distro, uname the kernel — together they fill both."""
    op_id = _op(client)
    host_id = _host(client, op_id)

    _upload(client, op_id, host_id, "uname_output", FIXTURES / "uname_output" / "uname-a.out")
    _upload(client, op_id, host_id, "os_release", FIXTURES / "os_release" / "os-release")

    host = client.get(f"/api/hosts/{host_id}").json()
    assert host["os_version"] == "Ubuntu 22.04.3 LTS"
    assert host["kernel_version"] == "5.15.0-88-generic"


def test_an_upload_never_overwrites_an_operator_supplied_value(client):
    """Fill-if-empty: the operator's edit outranks a later artifact."""
    op_id = _op(client)
    host_id = _host(client, op_id)
    client.patch(f"/api/hosts/{host_id}", json={"os_version": "hand-checked: Ubuntu 20.04"})

    _upload(client, op_id, host_id, "os_release", FIXTURES / "os_release" / "os-release")

    host = client.get(f"/api/hosts/{host_id}").json()
    assert host["os_version"] == "hand-checked: Ubuntu 20.04"


def test_system_info_lands_on_the_source_host_not_a_new_one(client):
    """These parsers describe metadata.host_id — they must create no host rows."""
    op_id = _op(client)
    host_id = _host(client, op_id)

    _upload(client, op_id, host_id, "uname_output", FIXTURES / "uname_output" / "uname-a.out")

    hosts = client.get(f"/api/ops/{op_id}/hosts").json()
    assert len(hosts) == 1
    assert hosts[0]["id"] == host_id
