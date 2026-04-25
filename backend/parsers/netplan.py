"""Parser for netplan YAML config (/etc/netplan/*.yaml).

Format example:

    network:
      version: 2
      ethernets:
        eth0:
          addresses: [10.0.0.5/24, 10.1.0.5/24]
          gateway4: 10.0.0.1
          routes:
            - to: default
              via: 10.0.0.1

Walks every interface section (`ethernets`, `wifis`, `bonds`, `bridges`,
`vlans`, `vrfs`, `modems`, `tunnels`) and harvests `addresses` entries
plus any `gateway4` / `gateway6` / `routes[*].via` values.

Per AGENT.md Phase 16: emits one HostData with the first IP as primary
and the rest as aliases. Gateways are NOT emitted as hosts. No
ConnectionData.
"""
from __future__ import annotations

import ipaddress
from typing import Any

from parsers import BaseParser, HostData, ParseResult, UploadMetadata

_INTERFACE_SECTIONS = (
    "ethernets", "wifis", "bonds", "bridges", "vlans", "vrfs",
    "modems", "tunnels",
)


def _strip_cidr(addr: str) -> str | None:
    if not isinstance(addr, str):
        return None
    a = addr.strip().split("/", 1)[0].split("%", 1)[0]  # also drop IPv6 zone id
    return a or None


def _is_routable(addr: str) -> bool:
    try:
        obj = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return not (obj.is_loopback or obj.is_multicast or obj.is_unspecified or obj.is_reserved)


def _harvest_addresses(value: Any, out: list[str]) -> None:
    """Walk `addresses:` value (list of strings or dict-like)."""
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                ip = _strip_cidr(item)
                if ip and _is_routable(ip):
                    out.append(ip)
            elif isinstance(item, dict):
                # Some netplan configs use {to: <ip/cidr>, lifetime: forever}
                for sub_v in item.values():
                    if isinstance(sub_v, str):
                        ip = _strip_cidr(sub_v)
                        if ip and _is_routable(ip):
                            out.append(ip)


def _harvest_gateways(iface: dict, out: list[str]) -> None:
    for key in ("gateway4", "gateway6"):
        v = iface.get(key)
        if isinstance(v, str):
            ip = _strip_cidr(v)
            if ip and _is_routable(ip):
                out.append(ip)
    routes = iface.get("routes") or []
    if isinstance(routes, list):
        for r in routes:
            if isinstance(r, dict):
                via = r.get("via")
                if isinstance(via, str):
                    ip = _strip_cidr(via)
                    if ip and _is_routable(ip):
                        out.append(ip)


class NetplanParser(BaseParser):
    """Parses netplan YAML."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Decode error: {e}")
            return result

        try:
            import yaml
        except ImportError as e:
            result.warnings.append(f"PyYAML unavailable: {e}")
            return result

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            result.warnings.append(f"YAML parse error: {e}")
            return result

        addrs: list[str] = []
        gateways: list[str] = []

        if not isinstance(data, dict):
            result.stats = {"addresses": 0, "gateways": 0}
            return result

        net = data.get("network") if isinstance(data.get("network"), dict) else None
        if net is None:
            result.stats = {"addresses": 0, "gateways": 0}
            return result

        for section_name in _INTERFACE_SECTIONS:
            section = net.get(section_name)
            if not isinstance(section, dict):
                continue
            for iface_name, iface in section.items():
                if not isinstance(iface, dict):
                    continue
                _harvest_addresses(iface.get("addresses"), addrs)
                _harvest_gateways(iface, gateways)

        all_addrs = list(dict.fromkeys(addrs))
        if all_addrs:
            primary = all_addrs[0]
            aliases = all_addrs[1:]
            result.hosts_found.append(HostData(
                ip_address=primary,
                aliases=aliases,
            ))

        result.stats = {
            "addresses": len(all_addrs),
            "gateways": len(gateways),
        }
        return result
