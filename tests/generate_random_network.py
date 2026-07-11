#!/usr/bin/env python3
"""
Generate a constrained-random network fixture for fuzz/variety testing.

Two ways to consume a random topology:
  - build_random_topology(rng, n_hosts=N)  — writes real RSA-key evidence files to
    disk and returns the file-based topology (the CLI / scenario fixture path).
  - build_structure_topology(rng, n_hosts=N) — an in-memory, structure-only export
    for invariant/scale runs: no keygen, no IO, distinct FAKE public-key blobs, in
    the shape tests/opbuilder consumes directly. Deterministic and golden-hashable.

Both share one deterministic core (_build_structure); only the CLI writes fixtures.

Constraints (so the topology stays testable):
  - N hosts (default random 5-8; --hosts to dial 5-200), each a random 10.20.x.y IP
  - max(2, N//8) RSA "keys" (shared across hosts to create pivots)
  - key pivots scale with host count; hosts form a DAG (no cycles)
  - at most one password path (optional)

Run with:
  uv run --project backend tests/generate_random_network.py [--seed N] [--hosts N]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import random
import struct
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
OUT = FIXTURES / "random_network"

_UTMP_FMT = "=hi32s4s32s256s4sl2l4i20s"
_UTMP_SIZE = struct.calcsize(_UTMP_FMT)
_TS = "Mar 15 14:20:00"

_USERS = ["alice", "root", "deploy", "ops", "svc"]

# Unique host IPs are drawn from 10.20.0-255.1-254 → 65024 distinct addresses.
# Beyond this the rejection sampler could never find a free IP, so we fail loudly.
_IP_CAPACITY = 256 * 254


# ─── Key helpers (paramiko imported lazily so structure-only runs need no keygen) ──

def gen_rsa_key():
    import paramiko
    return paramiko.RSAKey.generate(2048)


def key_to_pem(key) -> str:
    buf = io.StringIO()
    key.write_private_key(buf)
    return buf.getvalue()


def key_to_publine(key, comment: str = "") -> str:
    blob = base64.b64encode(key.asbytes()).decode()
    return f"ssh-rsa {blob}" + (f" {comment}" if comment else "")


def fingerprint(key) -> str:
    raw = bytes(key.asbytes())
    digest = hashlib.sha256(raw).digest()
    b64 = base64.b64encode(digest).decode().rstrip("=")
    return f"SHA256:{b64}"


# ─── File builders ────────────────────────────────────────────────────────────

def make_authorized_keys(keys: list[tuple]) -> str:
    return "\n".join(key_to_publine(k, c) for k, c in keys) + "\n"


def make_known_hosts(hosts: list[str], host_key) -> str:
    blob = base64.b64encode(host_key.asbytes()).decode()
    return "\n".join(f"{h} ssh-rsa {blob}" for h in hosts) + "\n"


def make_bash_history(commands: list[str]) -> str:
    return "\n".join(commands) + "\n"


def make_auth_log(hostname: str, entries: list[tuple]) -> str:
    lines = []
    for i, (user, from_ip, method, fp) in enumerate(entries):
        pid = 2000 + i
        if method == "publickey" and fp:
            lines.append(
                f"{_TS} {hostname} sshd[{pid}]: Accepted publickey for {user} "
                f"from {from_ip} port 52341 ssh2: RSA {fp}"
            )
        else:
            lines.append(
                f"{_TS} {hostname} sshd[{pid}]: Accepted password for {user} "
                f"from {from_ip} port 52341 ssh2"
            )
    return "\n".join(lines) + "\n"


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content)
    else:
        path.write_bytes(content)


# ─── Deterministic structural core ──────────────────────────────────────────────

def _resolve_sizes(rng: random.Random, n_hosts, n_keys) -> tuple[int, int]:
    """Default host count preserves the original random 5-8 first draw; key count
    scales with hosts. Both overridable (e.g. by --hosts / profiles.scale(n))."""
    if n_hosts is None:
        n_hosts = rng.randint(5, 8)
    if n_keys is None:
        n_keys = max(2, n_hosts // 8)
    return n_hosts, n_keys


def _build_structure(rng: random.Random, n_hosts: int, n_keys: int) -> dict:
    """All rng draws live here; no keygen, no IO. Keys referenced by NAME.

    Draw order is fixed so a (seed, n_hosts) pair is reproducible; new scaling draws
    are appended after the existing ones. Structural only — fingerprints/keys are
    added by the caller (fake for the in-memory export, real for the CLI).
    """
    if n_hosts <= 0:
        return {
            "n_hosts": 0, "n_keys": 0, "names": [], "ips": {}, "users": {},
            "key_names": [], "host_key": {}, "authorized": {},
            "key_pivots": [], "password_connections": [],
        }
    if n_hosts > _IP_CAPACITY:
        raise ValueError(f"n_hosts={n_hosts} exceeds the {_IP_CAPACITY}-address IP space")

    key_names = [f"key{i}" for i in range(n_keys)]
    names = [f"host{i:02d}" for i in range(n_hosts)]

    ips: dict[str, str] = {}
    used_ips: set[str] = set()
    for name in names:
        while True:
            ip = f"10.20.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
            if ip not in used_ips:
                used_ips.add(ip)
                ips[name] = ip
                break

    users = {name: rng.choice(_USERS) for name in names}
    # Each non-last host carries one private "outbound pivot key"; last host has none.
    host_key = {name: rng.choice(key_names) for name in names[:-1]}

    key_pivots: list[dict] = []
    authorized: dict[str, list[tuple]] = {n: [] for n in names}
    password_connections: list[dict] = []

    if n_hosts >= 2:
        edges_added: set[tuple[str, str]] = set()

        def _add_pivot(src_idx: int, dst_idx: int) -> None:
            src, dst = names[src_idx], names[dst_idx]
            if (src, dst) in edges_added:
                return
            edges_added.add((src, dst))
            kname = host_key[src]
            key_pivots.append({
                "src": src, "dst": dst,
                "src_user": users[src], "dst_user": users[dst], "key": kname,
            })
            authorized[dst].append((kname, f"{users[src]}@{src}"))

        # Key pivots scale with host count (DAG: src index < dst index).
        target = max(2, n_hosts // 3)
        attempts = 0
        while len(key_pivots) < target and attempts < target * 20:
            attempts += 1
            src_idx = rng.randint(0, n_hosts - 2)
            _add_pivot(src_idx, rng.randint(src_idx + 1, n_hosts - 1))

        # A scaled handful of extra pivots.
        for _ in range(rng.randint(0, max(2, n_hosts // 20))):
            src_idx = rng.randint(0, n_hosts - 2)
            _add_pivot(src_idx, rng.randint(src_idx + 1, n_hosts - 1))

        # Optional single password path.
        if rng.random() < 0.6:
            candidates = [
                (i, j) for i in range(n_hosts - 1) for j in range(i + 1, n_hosts)
                if (names[i], names[j]) not in edges_added
            ]
            if candidates:
                si, di = rng.choice(candidates)
                src, dst = names[si], names[di]
                edges_added.add((src, dst))
                password_connections.append({
                    "src": src, "dst": dst,
                    "src_user": users[src], "dst_user": users[dst],
                })

    return {
        "n_hosts": n_hosts, "n_keys": n_keys, "names": names, "ips": ips,
        "users": users, "key_names": key_names, "host_key": host_key,
        "authorized": authorized, "key_pivots": key_pivots,
        "password_connections": password_connections,
    }


def _fake_pubkey(key_name: str) -> str:
    """A distinct, valid-base64 public-key blob per key name → a distinct fingerprint
    at upload time, so independent keys never cross-link (shared keys still do)."""
    blob = base64.b64encode(f"lockpick-structkey-{key_name}".encode()).decode()
    return f"ssh-ed25519 {blob} {key_name}"


# ─── In-memory structure-only export (for scale / invariant runs) ────────────────

def build_structure_topology(rng: random.Random, *, n_hosts=None, n_keys=None) -> dict:
    """Deterministic, keygen-free topology in the shape tests/opbuilder consumes.

    Key pivots become public-key credentials (fake blobs) linked found_on_disk on the
    source host and authorized_key on the destination; password paths become manual
    connections. Golden-hashable (no set-order or key material in the output).
    """
    n_hosts, n_keys = _resolve_sizes(rng, n_hosts, n_keys)
    s = _build_structure(rng, n_hosts, n_keys)

    used_keys = set(s["host_key"].values())
    for links in s["authorized"].values():
        for kn, _comment in links:
            used_keys.add(kn)

    credentials = [
        {"key": kn, "cred_type": "public_key", "value": _fake_pubkey(kn), "name": kn}
        for kn in s["key_names"] if kn in used_keys
    ]

    credential_links: list[dict] = []
    for h in s["names"]:
        if h in s["host_key"]:
            credential_links.append({
                "credential": s["host_key"][h], "host": h,
                "relationship_type": "found_on_disk", "username": s["users"][h],
            })
    for h in s["names"]:
        for kn, _comment in s["authorized"][h]:
            credential_links.append({
                "credential": kn, "host": h,
                "relationship_type": "authorized_key", "username": s["users"][h],
            })

    connections = [
        {
            "src": c["src"], "dst": c["dst"],
            "src_user": c["src_user"], "dst_user": c["dst_user"],
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "auth_method": "password", "timestamp": None, "source_file": "generator",
        }
        for c in s["password_connections"]
    ]

    return {
        "n_hosts": s["n_hosts"], "n_keys": s["n_keys"],
        "hosts": [{"nickname": h, "ip": s["ips"][h], "files": []} for h in s["names"]],
        "credentials": credentials,
        "credential_links": credential_links,
        "connections": connections,
        "expected_key_pivots": s["key_pivots"],
        "expected_password_connections": s["password_connections"],
    }


# ─── File-based export (CLI / scenario fixture; real RSA keys) ────────────────────

def build_random_topology(rng: random.Random, *, n_hosts=None, n_keys=None, out_dir: Path = OUT) -> dict:
    """Materialize a random topology as real SSH-evidence files under ``out_dir`` and
    return the file-based topology (same schema as the static network's topology.json)."""
    n_hosts, n_keys = _resolve_sizes(rng, n_hosts, n_keys)
    s = _build_structure(rng, n_hosts, n_keys)
    users, ips = s["users"], s["ips"]

    keys = {kn: gen_rsa_key() for kn in s["key_names"]}
    fps = {kn: fingerprint(k) for kn, k in keys.items()}

    host_entries = []
    for h in s["names"]:
        files = []
        h_dir = out_dir / h

        if h in s["host_key"]:
            fname = f"{users[h]}_id_rsa"
            write(h_dir / fname, key_to_pem(keys[s["host_key"][h]]))
            files.append({"path": f"{h}/{fname}", "file_type": "private_key", "username": users[h]})

        if s["authorized"][h]:
            fname = f"{users[h]}_authorized_keys"
            write(h_dir / fname, make_authorized_keys([(keys[kn], c) for kn, c in s["authorized"][h]]))
            files.append({"path": f"{h}/{fname}", "file_type": "authorized_keys", "username": users[h]})

        auth_entries = []
        for pivot in s["key_pivots"]:
            if pivot["dst"] == h:
                auth_entries.append((pivot["dst_user"], ips[pivot["src"]], "publickey", fps[pivot["key"]]))
        for conn in s["password_connections"]:
            if conn["dst"] == h:
                auth_entries.append((conn["dst_user"], ips[conn["src"]], "password", None))
        if auth_entries:
            write(h_dir / "auth.log", make_auth_log(h, auth_entries))
            files.append({"path": f"{h}/auth.log", "file_type": "auth_log", "username": None})

        cmds = [f"ssh {p['dst_user']}@{ips[p['dst']]}" for p in s["key_pivots"] if p["src"] == h]
        cmds += [f"ssh {c['dst_user']}@{ips[c['dst']]}" for c in s["password_connections"] if c["src"] == h]
        if cmds:
            fname = f"{users[h]}_bash_history"
            write(h_dir / fname, make_bash_history(cmds))
            files.append({"path": f"{h}/{fname}", "file_type": "bash_history", "username": users[h]})

        destinations = [ips[p["dst"]] for p in s["key_pivots"] if p["src"] == h]
        destinations += [ips[c["dst"]] for c in s["password_connections"] if c["src"] == h]
        if destinations:
            kname = s["host_key"].get(h, s["key_names"][0])
            fname = f"{users[h]}_known_hosts"
            write(h_dir / fname, make_known_hosts(destinations, keys[kname]))
            files.append({"path": f"{h}/{fname}", "file_type": "known_hosts", "username": users[h]})

        host_entries.append({"nickname": h, "ip": ips[h], "files": files})

    return {
        "key_fingerprints": fps,
        "hosts": host_entries,
        "expected_key_pivots": s["key_pivots"],
        "expected_password_connections": s["password_connections"],
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None, help="Random seed (default: random)")
    parser.add_argument("--hosts", type=int, default=None, help="Host count 5-200 (default: random 5-8)")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randint(0, 2**31)
    print(f"Seed: {seed}")
    rng = random.Random(seed)

    print("Building random topology (generating RSA keys)...")
    topology = build_random_topology(rng, n_hosts=args.hosts)
    topology["seed"] = seed

    write(OUT / "topology.json", json.dumps(topology, indent=2))
    print(f"Random network written to: {OUT}")
    print(f"  {len(topology['hosts'])} hosts")
    print(f"  {len(topology['expected_key_pivots'])} key pivots")
    print(f"  {len(topology['expected_password_connections'])} password connections")
    print("Done.")


if __name__ == "__main__":
    main()
