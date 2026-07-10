"""OpBuilder — a thin, client-agnostic driver for the Lockpick REST API.

The builder mirrors the REST surface (``op / host / ip / upload / connection /
credential / credential_link / graph``) and asserts each endpoint's expected
status code. It duck-types the HTTP client, so the SAME code drives both the
pytest ``fastapi.testclient.TestClient`` (in-process) and an ``httpx.Client``
(live server, used by ``tests/e2e/seed_e2e.py``): both expose ``.post()`` /
``.get()`` and return a response with ``.status_code`` / ``.json()`` / ``.text``.

This package imports no production or pytest code so ``seed_e2e.py`` can import
it under a plain ``uv run python`` invocation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class LoadedOp:
    """The result of :meth:`OpBuilder.apply_topology`.

    Exposes attribute access (``lo.op_id``) for new code plus ``__getitem__``
    (``lo["op_id"]``) so it is a drop-in for the dict the pre-existing
    ``loaded_op`` scenario fixtures returned.
    """

    op_id: str
    host_ids: dict[str, str]
    topology: dict[str, Any]
    graph: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class OpBuilder:
    """Drives the REST API through any ``httpx``-shaped client."""

    def __init__(self, client: Any):
        self.client = client

    # ── Primitive endpoints (each asserts its own status code) ──────────────

    def op(self, name: str = "op", *, description: Optional[str] = None) -> str:
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        r = self.client.post("/api/ops", json=body)
        assert r.status_code == 201, f"POST /ops → {r.status_code}: {r.text}"
        return r.json()["id"]

    def host(self, op_id: str, nickname: str, *, comment: Optional[str] = None) -> str:
        body: dict[str, Any] = {"nickname": nickname}
        if comment is not None:
            body["comment"] = comment
        r = self.client.post(f"/api/ops/{op_id}/hosts", json=body)
        assert r.status_code == 201, f"POST /hosts → {r.status_code}: {r.text}"
        return r.json()["id"]

    def ip(self, host_id: str, ip_address: str, *, addr_type: str = "ipv4", source: str = "manual") -> dict:
        r = self.client.post(
            f"/api/hosts/{host_id}/ips",
            json={"ip_address": ip_address, "addr_type": addr_type, "source": source},
        )
        assert r.status_code == 201, f"POST /ips → {r.status_code}: {r.text}"
        return r.json()

    def upload(
        self,
        op_id: str,
        host_id: str,
        file_type: str,
        content: bytes,
        filename: str,
        username: Optional[str] = None,
    ) -> dict:
        data: dict[str, Any] = {"file_type": file_type, "host_id": host_id}
        if username:
            data["username"] = username
        r = self.client.post(
            f"/api/ops/{op_id}/upload",
            data=data,
            files={"file": (filename, content, "application/octet-stream")},
        )
        assert r.status_code == 200, f"POST /upload {filename} → {r.status_code}: {r.text}"
        return r.json()

    def connection(
        self,
        op_id: str,
        *,
        src_ip: str,
        dst_ip: str,
        src_host_id: Optional[str] = None,
        dst_host_id: Optional[str] = None,
        src_user: Optional[str] = None,
        dst_user: Optional[str] = None,
        connection_type: str = "ssh",
        direction_context: str = "from_dst_logs",
        auth_method: Optional[str] = None,
        timestamp: Optional[str] = None,
        credential_id: Optional[str] = None,
        raw_line: Optional[str] = None,
        source_file: str = "opbuilder",
    ) -> dict:
        body = {
            "src_host_id": src_host_id,
            "src_ip": src_ip,
            "src_user": src_user,
            "dst_host_id": dst_host_id,
            "dst_ip": dst_ip,
            "dst_user": dst_user,
            "connection_type": connection_type,
            "direction_context": direction_context,
            "auth_method": auth_method,
            "credential_id": credential_id,
            "timestamp": timestamp,
            "raw_line": raw_line,
            "source_file": source_file,
        }
        r = self.client.post(f"/api/ops/{op_id}/connections", json=body)
        assert r.status_code == 201, f"POST /connections → {r.status_code}: {r.text}"
        return r.json()

    def credential(
        self,
        op_id: str,
        *,
        cred_type: str,
        value: str,
        name: Optional[str] = None,
        passphrase: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        body: dict[str, Any] = {"cred_type": cred_type, "value": value}
        if name is not None:
            body["name"] = name
        if passphrase is not None:
            body["passphrase"] = passphrase
        if comment is not None:
            body["comment"] = comment
        r = self.client.post(f"/api/ops/{op_id}/credentials", json=body)
        assert r.status_code == 201, f"POST /credentials → {r.status_code}: {r.text}"
        return r.json()["id"]

    def credential_link(
        self,
        *,
        credential_id: str,
        host_id: str,
        relationship_type: str,
        username: Optional[str] = None,
        host_user_id: Optional[str] = None,
        file_source: Optional[str] = None,
    ) -> str:
        body: dict[str, Any] = {
            "credential_id": credential_id,
            "host_id": host_id,
            "relationship_type": relationship_type,
        }
        if username is not None:
            body["username"] = username
        if host_user_id is not None:
            body["host_user_id"] = host_user_id
        if file_source is not None:
            body["file_source"] = file_source
        r = self.client.post("/api/credential-links", json=body)
        assert r.status_code == 201, f"POST /credential-links → {r.status_code}: {r.text}"
        return r.json()["id"]

    def graph(self, op_id: str) -> dict:
        r = self.client.get(f"/api/ops/{op_id}/graph")
        assert r.status_code == 200, f"GET /graph → {r.status_code}: {r.text}"
        return r.json()

    # ── High-level composition ──────────────────────────────────────────────

    def apply_topology(
        self,
        topology: dict[str, Any],
        fixtures_root: Optional[Path] = None,
        *,
        name: Optional[str] = None,
    ) -> LoadedOp:
        """Create an op and replay a topology dict against the REST API.

        Steps, in order: create op → create every host + register its IP →
        upload every host's files → create credentials + credential-links →
        create connections → fetch the graph. Mirrors (and subsumes) the
        hosts→uploads→connections recipe the scenario fixtures and the e2e seed
        hand-rolled.

        ``fixtures_root`` resolves relative ``file["path"]`` entries; absolute
        paths are used as-is.
        """
        root = Path(fixtures_root) if fixtures_root is not None else None
        op_name = name or topology.get("name") or "op"
        op_id = self.op(op_name)

        # 1. Hosts + IPs (all hosts first, so later connections can reference any).
        host_ids: dict[str, str] = {}
        host_ips: dict[str, str] = {}
        for h in topology.get("hosts", []):
            hid = self.host(op_id, h["nickname"])
            host_ids[h["nickname"]] = hid
            if h.get("ip"):
                self.ip(hid, h["ip"])
                host_ips[h["nickname"]] = h["ip"]

        # 2. File uploads (per host, in declared order).
        for h in topology.get("hosts", []):
            hid = host_ids[h["nickname"]]
            for f in h.get("files", []):
                path = Path(f["path"])
                if root is not None and not path.is_absolute():
                    path = root / path
                self.upload(
                    op_id,
                    hid,
                    f["file_type"],
                    path.read_bytes(),
                    path.name,
                    f.get("username"),
                )

        # 3. Credentials + credential-links (keyed by a topology-local alias).
        cred_ids: dict[str, str] = {}
        for c in topology.get("credentials", []):
            cred_ids[c["key"]] = self.credential(
                op_id,
                cred_type=c["cred_type"],
                value=c["value"],
                name=c.get("name"),
                passphrase=c.get("passphrase"),
                comment=c.get("comment"),
            )
        for link in topology.get("credential_links", []):
            self.credential_link(
                credential_id=cred_ids[link["credential"]],
                host_id=host_ids[link["host"]],
                relationship_type=link["relationship_type"],
                username=link.get("username"),
                file_source=link.get("file_source"),
            )

        # 4. Connections (nickname endpoints resolved to host ids + IPs).
        for conn in topology.get("connections", []):
            self.connection(
                op_id,
                src_host_id=host_ids[conn["src"]],
                src_ip=host_ips[conn["src"]],
                src_user=conn.get("src_user"),
                dst_host_id=host_ids[conn["dst"]],
                dst_ip=host_ips[conn["dst"]],
                dst_user=conn.get("dst_user"),
                connection_type=conn.get("connection_type", "ssh"),
                direction_context=conn.get("direction_context", "from_dst_logs"),
                auth_method=conn.get("auth_method"),
                timestamp=conn.get("timestamp"),
                source_file=conn.get("source_file", "opbuilder"),
            )

        return LoadedOp(
            op_id=op_id,
            host_ids=host_ids,
            topology=topology,
            graph=self.graph(op_id),
        )
