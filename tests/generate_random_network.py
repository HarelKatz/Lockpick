#!/usr/bin/env python3
"""
Generate a constrained-random network fixture for fuzz/variety testing.

Produces:
  tests/fixtures/random_network/  — N hosts with SSH evidence files + topology.json

Constraints (so the topology stays testable):
  - 5–8 hosts, each with a random RFC-1918 IP in 10.20.x.y
  - 2–4 RSA key pairs (shared across hosts to create pivots)
  - At least 2 key-based pivot paths
  - At most 1 password-based path (optional)
  - Hosts are a DAG — no cycles in the pivot graph

Run with:
  uv run --project backend tests/generate_random_network.py [--seed N]
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

import paramiko

FIXTURES = Path(__file__).parent / "fixtures"
OUT = FIXTURES / "random_network"

_UTMP_FMT = "=hi32s4s32s256s4sl2l4i20s"
_UTMP_SIZE = struct.calcsize(_UTMP_FMT)
_TS = "Mar 15 14:20:00"


# ─── Key helpers ──────────────────────────────────────────────────────────────

def gen_rsa_key() -> paramiko.RSAKey:
    return paramiko.RSAKey.generate(2048)


def key_to_pem(key: paramiko.RSAKey) -> str:
    buf = io.StringIO()
    key.write_private_key(buf)
    return buf.getvalue()


def key_to_publine(key: paramiko.RSAKey, comment: str = "") -> str:
    blob = base64.b64encode(key.asbytes()).decode()
    return f"ssh-rsa {blob}" + (f" {comment}" if comment else "")


def fingerprint(key: paramiko.RSAKey) -> str:
    raw = bytes(key.asbytes())
    digest = hashlib.sha256(raw).digest()
    b64 = base64.b64encode(digest).decode().rstrip("=")
    return f"SHA256:{b64}"


# ─── File builders ────────────────────────────────────────────────────────────

def make_authorized_keys(keys: list[tuple[paramiko.RSAKey, str]]) -> str:
    return "\n".join(key_to_publine(k, c) for k, c in keys) + "\n"


def make_known_hosts(hosts: list[str], host_key: paramiko.RSAKey) -> str:
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


# ─── Topology builder ─────────────────────────────────────────────────────────

def build_random_topology(rng: random.Random) -> dict:
    """
    Build a random DAG of hosts with key-based and optional password pivots.
    Returns a topology dict (same schema as the static network's topology.json).
    """
    n_hosts = rng.randint(5, 8)
    n_keys = rng.randint(2, 4)

    print(f"  Hosts: {n_hosts}, Keys: {n_keys}")

    # Generate key pairs
    key_names = [f"key{i}" for i in range(n_keys)]
    print("  Generating RSA keys...")
    keys = {name: gen_rsa_key() for name in key_names}
    fps = {name: fingerprint(k) for name, k in keys.items()}

    # Assign host names and IPs
    names = [f"host{i:02d}" for i in range(n_hosts)]
    ips = {}
    used_ips: set[str] = set()
    for name in names:
        while True:
            ip = f"10.20.{rng.randint(0, 5)}.{rng.randint(1, 254)}"
            if ip not in used_ips:
                used_ips.add(ip)
                ips[name] = ip
                break

    # Assign a "primary user" per host for simplicity
    users = {name: rng.choice(["alice", "root", "deploy", "ops", "svc"]) for name in names}

    # Assign one key per host as the "outbound pivot key" (private key found on this host)
    host_key = {name: rng.choice(key_names) for name in names[:-1]}  # last host has no outbound key

    # Build key-based pivot edges (DAG: only allow src_idx < dst_idx)
    key_pivots: list[dict] = []
    authorized: dict[str, list[tuple]] = {n: [] for n in names}  # name → [(key, comment)]

    # Ensure at least 2 key pivots
    edges_added: set[tuple[str, str]] = set()
    attempts = 0
    while len(key_pivots) < 2 and attempts < 50:
        attempts += 1
        src_idx = rng.randint(0, n_hosts - 2)
        dst_idx = rng.randint(src_idx + 1, n_hosts - 1)
        src = names[src_idx]
        dst = names[dst_idx]
        if (src, dst) in edges_added:
            continue
        edges_added.add((src, dst))
        kname = host_key.get(src, rng.choice(key_names))
        src_user = users[src]
        dst_user = users[dst]
        key_pivots.append({
            "src": src, "dst": dst,
            "src_user": src_user, "dst_user": dst_user,
            "key": kname,
        })
        authorized[dst].append((keys[kname], f"{src_user}@{src}"))

    # Add a few more random key pivots
    for _ in range(rng.randint(0, 2)):
        src_idx = rng.randint(0, n_hosts - 2)
        dst_idx = rng.randint(src_idx + 1, n_hosts - 1)
        src, dst = names[src_idx], names[dst_idx]
        if (src, dst) in edges_added:
            continue
        edges_added.add((src, dst))
        kname = host_key.get(src, rng.choice(key_names))
        src_user, dst_user = users[src], users[dst]
        key_pivots.append({
            "src": src, "dst": dst,
            "src_user": src_user, "dst_user": dst_user,
            "key": kname,
        })
        authorized[dst].append((keys[kname], f"{src_user}@{src}"))

    # Optional password pivot
    password_connections: list[dict] = []
    if rng.random() < 0.6:
        candidates = [(i, j) for i in range(n_hosts - 1) for j in range(i + 1, n_hosts)
                      if (names[i], names[j]) not in edges_added]
        if candidates:
            si, di = rng.choice(candidates)
            src, dst = names[si], names[di]
            edges_added.add((src, dst))
            su, du = users[src], users[dst]
            password_connections.append({"src": src, "dst": dst, "src_user": su, "dst_user": du})

    # ── Build per-host file manifests ─────────────────────────────────────────
    host_entries = []
    for h in names:
        files = []
        h_dir = OUT / h

        # Private key (found on this host)
        if h in host_key:
            kname = host_key[h]
            fname = f"{users[h]}_id_rsa"
            write(h_dir / fname, key_to_pem(keys[kname]))
            files.append({"path": f"{h}/{fname}", "file_type": "private_key", "username": users[h]})

        # Authorized keys (if other hosts' keys are authorized here)
        if authorized[h]:
            fname = f"{users[h]}_authorized_keys"
            write(h_dir / fname, make_authorized_keys(authorized[h]))
            files.append({"path": f"{h}/{fname}", "file_type": "authorized_keys", "username": users[h]})

        # Auth log: accepted connections inbound to this host
        auth_entries = []
        for pivot in key_pivots:
            if pivot["dst"] == h:
                auth_entries.append((
                    pivot["dst_user"],
                    ips[pivot["src"]],
                    "publickey",
                    fps[pivot["key"]],
                ))
        for conn in password_connections:
            if conn["dst"] == h:
                auth_entries.append((conn["dst_user"], ips[conn["src"]], "password", None))
        if auth_entries:
            fname = "auth.log"
            write(h_dir / fname, make_auth_log(h, auth_entries))
            files.append({"path": f"{h}/{fname}", "file_type": "auth_log", "username": None})

        # Bash history: outbound ssh commands from this host
        outbound = [p for p in key_pivots if p["src"] == h]
        outbound_pw = [c for c in password_connections if c["src"] == h]
        cmds = []
        for p in outbound:
            cmds.append(f"ssh {p['dst_user']}@{ips[p['dst']]}")
        for c in outbound_pw:
            cmds.append(f"ssh {c['dst_user']}@{ips[c['dst']]}")
        if cmds:
            fname = f"{users[h]}_bash_history"
            write(h_dir / fname, make_bash_history(cmds))
            files.append({"path": f"{h}/{fname}", "file_type": "bash_history", "username": users[h]})

        # Known hosts: destinations this host connected to
        destinations = [ips[p["dst"]] for p in key_pivots if p["src"] == h]
        destinations += [ips[c["dst"]] for c in password_connections if c["src"] == h]
        if destinations:
            kname = host_key.get(h, key_names[0])
            fname = f"{users[h]}_known_hosts"
            write(h_dir / fname, make_known_hosts(destinations, keys[kname]))
            files.append({"path": f"{h}/{fname}", "file_type": "known_hosts", "username": users[h]})

        host_entries.append({
            "nickname": h,
            "ip": ips[h],
            "files": files,
        })

    return {
        "key_fingerprints": fps,
        "hosts": host_entries,
        "expected_key_pivots": key_pivots,
        "expected_password_connections": password_connections,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None, help="Random seed (default: random)")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randint(0, 2**31)
    print(f"Seed: {seed}")
    rng = random.Random(seed)

    print("Building random topology...")
    topology = build_random_topology(rng)
    topology["seed"] = seed

    write(OUT / "topology.json", json.dumps(topology, indent=2))
    print(f"Random network written to: {OUT}")
    print(f"  {len(topology['hosts'])} hosts")
    print(f"  {len(topology['expected_key_pivots'])} key pivots")
    print(f"  {len(topology['expected_password_connections'])} password connections")
    print("Done.")


if __name__ == "__main__":
    main()
