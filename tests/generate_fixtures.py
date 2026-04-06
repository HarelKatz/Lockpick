#!/usr/bin/env python3
"""
Generate static network fixtures for integration tests.

Produces:
  tests/fixtures/network/  — 10-host static network with SSH evidence files
  tests/fixtures/bad/      — corrupt/malformed files for parser robustness tests

Run with:
  uv run --project backend tests/generate_fixtures.py
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import struct
from pathlib import Path

import paramiko

FIXTURES = Path(__file__).parent / "fixtures"
NET = FIXTURES / "network"
BAD = FIXTURES / "bad"

# Timestamp used throughout — fixed for determinism
_TS = "Mar 15 14:20:00"

# utmp record format (matches backend/parsers/wtmp.py)
_UTMP_FMT = "=hi32s4s32s256s4sl2l4i20s"
_UTMP_SIZE = struct.calcsize(_UTMP_FMT)


# ─── Key helpers ──────────────────────────────────────────────────────────────

def gen_rsa_key(bits: int = 2048) -> paramiko.RSAKey:
    return paramiko.RSAKey.generate(bits)


def key_to_pem(key: paramiko.RSAKey) -> str:
    buf = io.StringIO()
    key.write_private_key(buf)
    return buf.getvalue()


def key_to_publine(key: paramiko.RSAKey, comment: str = "") -> str:
    blob = base64.b64encode(key.asbytes()).decode()
    parts = ["ssh-rsa", blob]
    if comment:
        parts.append(comment)
    return " ".join(parts)


def fingerprint(key: paramiko.RSAKey) -> str:
    raw = bytes(key.asbytes())
    digest = hashlib.sha256(raw).digest()
    b64 = base64.b64encode(digest).decode().rstrip("=")
    return f"SHA256:{b64}"


# ─── File content builders ─────────────────────────────────────────────────────

def make_authorized_keys(keys: list[tuple[paramiko.RSAKey, str]]) -> str:
    return "\n".join(key_to_publine(k, c) for k, c in keys) + "\n"


def make_known_hosts(hosts: list[str], host_key: paramiko.RSAKey) -> str:
    """Known_hosts entries — uses host_key as the server host key (content doesn't affect parsing)."""
    blob = base64.b64encode(host_key.asbytes()).decode()
    return "\n".join(f"{h} ssh-rsa {blob}" for h in hosts) + "\n"


def make_bash_history(commands: list[str]) -> str:
    return "\n".join(commands) + "\n"


def make_auth_log(hostname: str, entries: list[tuple]) -> str:
    """entries: list of (user, from_ip, method, fp_or_none)"""
    lines = []
    for i, (user, from_ip, method, fp) in enumerate(entries):
        pid = 1000 + i
        if method == "publickey" and fp:
            line = (
                f"{_TS} {hostname} sshd[{pid}]: Accepted publickey for {user} "
                f"from {from_ip} port 52341 ssh2: RSA {fp}"
            )
        elif method == "password":
            line = (
                f"{_TS} {hostname} sshd[{pid}]: Accepted password for {user} "
                f"from {from_ip} port 52341 ssh2"
            )
        else:
            line = (
                f"{_TS} {hostname} sshd[{pid}]: Accepted {method} for {user} "
                f"from {from_ip} port 52341 ssh2"
            )
        lines.append(line)
    return "\n".join(lines) + "\n"


def make_wtmp_record(user: str, src_ip: str, ts_sec: int) -> bytes:
    """Build a single utmp record compatible with the wtmp parser."""
    ut_line = b"pts/0\x00" + b"\x00" * 26
    ut_id = b"0\x00\x00\x00"
    ut_user = user.encode()[:32].ljust(32, b"\x00")
    ut_host = src_ip.encode()[:256].ljust(256, b"\x00")
    ut_exit = b"\x00" * 4
    parts = [int(x) for x in src_ip.split(".")]
    addr0 = parts[0] | (parts[1] << 8) | (parts[2] << 16) | (parts[3] << 24)
    return struct.pack(
        _UTMP_FMT,
        7,        # UT_USER_PROCESS
        1234,     # ut_pid
        ut_line,
        ut_id,
        ut_user,
        ut_host,
        ut_exit,
        0,        # ut_session
        ts_sec,   # tv_sec
        0,        # tv_usec
        addr0, 0, 0, 0,   # ut_addr_v6
        b"\x00" * 20,     # __unused
    )


# ─── File I/O ─────────────────────────────────────────────────────────────────

def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content)
    else:
        path.write_bytes(content)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Generating RSA keys (2048-bit, this takes a moment)...")
    alice_key = gen_rsa_key()
    root_key = gen_rsa_key()
    deploy_key = gen_rsa_key()
    backup_key = gen_rsa_key()

    fps = {
        "alice_key": fingerprint(alice_key),
        "root_key": fingerprint(root_key),
        "deploy_key": fingerprint(deploy_key),
        "backup_key": fingerprint(backup_key),
    }
    for name, fp in fps.items():
        print(f"  {name}: {fp}")

    # ── attackbox (10.10.0.10) ────────────────────────────────────────────────
    # alice's private key is found here; she SSHes to jumpbox, webserver, backup
    d = NET / "attackbox"
    write(d / "alice_id_rsa", key_to_pem(alice_key))
    write(d / "alice_authorized_keys", make_authorized_keys([
        (alice_key, "alice@attackbox"),
    ]))
    write(d / "alice_bash_history", make_bash_history([
        "ls -la /home",
        "ssh alice@10.10.0.1",
        "ssh alice@10.10.1.10",
        "ssh alice@10.10.1.30",
        "scp report.txt alice@10.10.0.1:/tmp/",
        "ssh-keygen -t rsa -f /tmp/testkey",
    ]))
    write(d / "alice_known_hosts", make_known_hosts(
        ["10.10.0.1", "10.10.1.10", "10.10.1.30"], alice_key,
    ))

    # ── jumpbox (10.10.0.1) ───────────────────────────────────────────────────
    # alice is authorized here; root has root_key + backup_key private keys
    d = NET / "jumpbox"
    write(d / "root_id_rsa", key_to_pem(root_key))
    write(d / "root_backup_id_rsa", key_to_pem(backup_key))   # root also holds backup_key
    write(d / "alice_authorized_keys", make_authorized_keys([
        (alice_key, "alice@attackbox"),
    ]))
    write(d / "root_authorized_keys", make_authorized_keys([
        (root_key, "root@jumpbox"),
    ]))
    write(d / "root_bash_history", make_bash_history([
        "ssh root@10.10.1.20",
        "ssh backup@10.10.1.30",
        "tail -f /var/log/auth.log",
    ]))
    write(d / "root_known_hosts", make_known_hosts(
        ["10.10.1.20", "10.10.1.30"], root_key,
    ))
    write(d / "auth.log", make_auth_log("jumpbox", [
        ("alice", "10.10.0.10", "publickey", fps["alice_key"]),
    ]))

    # ── dbserver (10.10.1.20) ─────────────────────────────────────────────────
    # root (from jumpbox) is authorized; deploy has deploy_key and connects to internal
    d = NET / "dbserver"
    write(d / "deploy_id_rsa", key_to_pem(deploy_key))
    write(d / "root_authorized_keys", make_authorized_keys([
        (root_key, "root@jumpbox"),
    ]))
    write(d / "deploy_authorized_keys", make_authorized_keys([
        (deploy_key, "deploy@dbserver"),
    ]))
    write(d / "deploy_bash_history", make_bash_history([
        "ssh deploy@10.10.2.5",
        "rsync -avz /var/backups/ deploy@10.10.2.5:/backups/",
    ]))
    write(d / "deploy_known_hosts", make_known_hosts(["10.10.2.5"], deploy_key))
    write(d / "auth.log", make_auth_log("dbserver", [
        ("root", "10.10.0.1", "publickey", fps["root_key"]),
    ]))

    # ── webserver (10.10.1.10) ────────────────────────────────────────────────
    # alice (from attackbox) is authorized
    d = NET / "webserver"
    write(d / "alice_authorized_keys", make_authorized_keys([
        (alice_key, "alice@attackbox"),
    ]))
    write(d / "auth.log", make_auth_log("webserver", [
        ("alice", "10.10.0.10", "publickey", fps["alice_key"]),
    ]))

    # ── backup (10.10.1.30) ───────────────────────────────────────────────────
    # two authorized keys: alice_key (from attackbox) and backup_key (from jumpbox/root)
    d = NET / "backup"
    write(d / "backup_authorized_keys", make_authorized_keys([
        (alice_key, "alice@attackbox"),
        (backup_key, "root@jumpbox"),
    ]))
    write(d / "auth.log", make_auth_log("backup", [
        ("backup", "10.10.0.10", "publickey", fps["alice_key"]),
        ("backup", "10.10.0.1", "publickey", fps["backup_key"]),
    ]))

    # ── internal (10.10.2.5) ──────────────────────────────────────────────────
    # deploy (from dbserver) is authorized
    d = NET / "internal"
    write(d / "deploy_authorized_keys", make_authorized_keys([
        (deploy_key, "deploy@dbserver"),
    ]))
    write(d / "auth.log", make_auth_log("internal", [
        ("deploy", "10.10.1.20", "publickey", fps["deploy_key"]),
    ]))

    # ── pentest_vm (10.10.0.20) ───────────────────────────────────────────────
    # ops user connects to citrix via password
    d = NET / "pentest_vm"
    write(d / "ops_bash_history", make_bash_history([
        "ssh ops@10.10.0.50",
        "ssh-copy-id ops@10.10.0.50",
    ]))
    write(d / "ops_known_hosts", make_known_hosts(["10.10.0.50"], alice_key))

    # ── citrix (10.10.0.50) ───────────────────────────────────────────────────
    # password login from pentest_vm; ops then connects to fileserver
    d = NET / "citrix"
    write(d / "auth.log", make_auth_log("citrix", [
        ("ops", "10.10.0.20", "password", None),
    ]))
    write(d / "ops_bash_history", make_bash_history(["ssh ops@10.10.3.10"]))
    write(d / "ops_known_hosts", make_known_hosts(["10.10.3.10"], alice_key))

    # ── fileserver (10.10.3.10) ───────────────────────────────────────────────
    # password login from citrix
    d = NET / "fileserver"
    write(d / "auth.log", make_auth_log("fileserver", [
        ("ops", "10.10.0.50", "password", None),
    ]))

    # ── monitoring (10.10.99.1) ───────────────────────────────────────────────
    # isolated — no connections, just create the directory
    (NET / "monitoring").mkdir(parents=True, exist_ok=True)

    # ─── Bad / corrupt files ──────────────────────────────────────────────────
    print("Generating bad/corrupt fixture files...")

    # Truncated private key (cut halfway through PEM)
    pem = key_to_pem(alice_key)
    write(BAD / "truncated_private_key", pem[: len(pem) // 2])

    # Binary garbage
    write(BAD / "binary_garbage", bytes(range(256)) * 4)

    # Valid gzip of non-log content
    write(BAD / "garbage.gz", gzip.compress(b"this is not an auth log\n" * 10))

    # Empty file
    write(BAD / "empty_file", b"")

    # Auth.log with no sshd lines
    write(BAD / "no_sshd.log", (
        "Mar 15 14:00:00 host kernel: random: crng init done\n"
        "Mar 15 14:01:00 host cron[123]: job started\n"
    ))

    # Authorized_keys where every line is malformed
    write(BAD / "malformed_authorized_keys", (
        "not-a-keytype AAAA== comment\n"
        "not a key at all\n"
        "\n"
        "   \n"
    ))

    # Public key submitted as if it were a private key
    write(BAD / "pubkey_as_private", key_to_publine(alice_key, "alice@attackbox") + "\n")

    # Wtmp file whose size is not a multiple of the utmp record size
    write(BAD / "wrong_size.wtmp", b"\x00" * 100)

    # ─── topology.json ────────────────────────────────────────────────────────
    topology = {
        "key_fingerprints": fps,
        "hosts": [
            {
                "nickname": "attackbox",
                "ip": "10.10.0.10",
                "files": [
                    {"path": "attackbox/alice_id_rsa",           "file_type": "private_key",     "username": "alice"},
                    {"path": "attackbox/alice_authorized_keys",  "file_type": "authorized_keys", "username": "alice"},
                    {"path": "attackbox/alice_bash_history",     "file_type": "bash_history",    "username": "alice"},
                    {"path": "attackbox/alice_known_hosts",      "file_type": "known_hosts",     "username": "alice"},
                ],
            },
            {
                "nickname": "jumpbox",
                "ip": "10.10.0.1",
                "files": [
                    {"path": "jumpbox/root_id_rsa",              "file_type": "private_key",     "username": "root"},
                    {"path": "jumpbox/root_backup_id_rsa",       "file_type": "private_key",     "username": "root"},
                    {"path": "jumpbox/alice_authorized_keys",    "file_type": "authorized_keys", "username": "alice"},
                    {"path": "jumpbox/root_authorized_keys",     "file_type": "authorized_keys", "username": "root"},
                    {"path": "jumpbox/root_bash_history",        "file_type": "bash_history",    "username": "root"},
                    {"path": "jumpbox/root_known_hosts",         "file_type": "known_hosts",     "username": "root"},
                    {"path": "jumpbox/auth.log",                 "file_type": "auth_log",        "username": None},
                ],
            },
            {
                "nickname": "dbserver",
                "ip": "10.10.1.20",
                "files": [
                    {"path": "dbserver/deploy_id_rsa",           "file_type": "private_key",     "username": "deploy"},
                    {"path": "dbserver/root_authorized_keys",    "file_type": "authorized_keys", "username": "root"},
                    {"path": "dbserver/deploy_authorized_keys",  "file_type": "authorized_keys", "username": "deploy"},
                    {"path": "dbserver/deploy_bash_history",     "file_type": "bash_history",    "username": "deploy"},
                    {"path": "dbserver/deploy_known_hosts",      "file_type": "known_hosts",     "username": "deploy"},
                    {"path": "dbserver/auth.log",                "file_type": "auth_log",        "username": None},
                ],
            },
            {
                "nickname": "webserver",
                "ip": "10.10.1.10",
                "files": [
                    {"path": "webserver/alice_authorized_keys",  "file_type": "authorized_keys", "username": "alice"},
                    {"path": "webserver/auth.log",               "file_type": "auth_log",        "username": None},
                ],
            },
            {
                "nickname": "backup",
                "ip": "10.10.1.30",
                "files": [
                    {"path": "backup/backup_authorized_keys",    "file_type": "authorized_keys", "username": "backup"},
                    {"path": "backup/auth.log",                  "file_type": "auth_log",        "username": None},
                ],
            },
            {
                "nickname": "internal",
                "ip": "10.10.2.5",
                "files": [
                    {"path": "internal/deploy_authorized_keys",  "file_type": "authorized_keys", "username": "deploy"},
                    {"path": "internal/auth.log",                "file_type": "auth_log",        "username": None},
                ],
            },
            {
                "nickname": "pentest_vm",
                "ip": "10.10.0.20",
                "files": [
                    {"path": "pentest_vm/ops_bash_history",      "file_type": "bash_history",    "username": "ops"},
                    {"path": "pentest_vm/ops_known_hosts",       "file_type": "known_hosts",     "username": "ops"},
                ],
            },
            {
                "nickname": "citrix",
                "ip": "10.10.0.50",
                "files": [
                    {"path": "citrix/auth.log",                  "file_type": "auth_log",        "username": None},
                    {"path": "citrix/ops_bash_history",          "file_type": "bash_history",    "username": "ops"},
                    {"path": "citrix/ops_known_hosts",           "file_type": "known_hosts",     "username": "ops"},
                ],
            },
            {
                "nickname": "fileserver",
                "ip": "10.10.3.10",
                "files": [
                    {"path": "fileserver/auth.log",              "file_type": "auth_log",        "username": None},
                ],
            },
            {
                "nickname": "monitoring",
                "ip": "10.10.99.1",
                "files": [],
            },
        ],
        "expected_key_pivots": [
            {"src": "attackbox",  "dst": "jumpbox",    "src_user": "alice",  "dst_user": "alice",  "key": "alice_key"},
            {"src": "attackbox",  "dst": "webserver",  "src_user": "alice",  "dst_user": "alice",  "key": "alice_key"},
            {"src": "attackbox",  "dst": "backup",     "src_user": "alice",  "dst_user": "backup", "key": "alice_key"},
            {"src": "jumpbox",    "dst": "dbserver",   "src_user": "root",   "dst_user": "root",   "key": "root_key"},
            {"src": "jumpbox",    "dst": "backup",     "src_user": "root",   "dst_user": "backup", "key": "backup_key"},
            {"src": "dbserver",   "dst": "internal",   "src_user": "deploy", "dst_user": "deploy", "key": "deploy_key"},
        ],
        "expected_password_connections": [
            {"src": "pentest_vm", "dst": "citrix",     "src_user": "ops",    "dst_user": "ops"},
            {"src": "citrix",     "dst": "fileserver", "src_user": "ops",    "dst_user": "ops"},
        ],
    }

    write(NET / "topology.json", json.dumps(topology, indent=2))
    print(f"Network fixtures written to: {NET}")
    print(f"Bad fixtures written to:     {BAD}")
    print("Done.")


if __name__ == "__main__":
    main()
