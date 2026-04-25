"""Unit tests for the docker_ps parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.docker_ps import DockerPsParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "docker_ps"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="docker_ps")


def test_emits_nothing_when_no_container_ip_visible():
    """Default `docker ps` output has port mappings but no container IPs.
    Parser should NOT fabricate hosts from port-mapping IPs.
    """
    content = (FIXTURES / "docker_ps_no_ip.out").read_bytes()
    result = DockerPsParser().parse(content, _meta())
    assert result.hosts_found == []
    assert result.stats == {"containers": 0}


def test_emits_host_per_container_with_ip():
    """Custom `--format` output containing container IPs → 2 HostData."""
    content = (FIXTURES / "docker_ps_with_ip.out").read_bytes()
    result = DockerPsParser().parse(content, _meta())
    assert len(result.hosts_found) == 2

    by_ip = {h.ip_address: h for h in result.hosts_found}
    assert "172.18.0.2" in by_ip
    assert "172.18.0.3" in by_ip
    # Container name preserved as nickname (last whitespace-separated token)
    assert by_ip["172.18.0.2"].nickname == "webserver"
    assert by_ip["172.18.0.3"].nickname == "redis-cache"


def test_loopback_and_link_local_skipped():
    content = (
        b"CONTAINER ID   IP             IMAGE         NAMES\n"
        b"abc123def456   127.0.0.1      foo:latest    container-x\n"
        b"def456abc123   169.254.0.1    bar:latest    container-y\n"
    )
    result = DockerPsParser().parse(content, _meta())
    assert result.hosts_found == []


def test_dedupes_repeated_ips():
    content = (
        b"CONTAINER ID   IP             IMAGE         NAMES\n"
        b"abc123def456   172.18.0.2     foo:latest    container-x\n"
        b"def456abc123   172.18.0.2     bar:latest    container-y\n"
    )
    result = DockerPsParser().parse(content, _meta())
    assert len(result.hosts_found) == 1


def test_empty_file():
    result = DockerPsParser().parse(b"", _meta())
    assert result.hosts_found == []
    assert result.stats == {"containers": 0}
