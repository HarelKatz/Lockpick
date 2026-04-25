"""Maps file_type strings to parser classes.

Centralises the parser registry so upload.py is decoupled from individual
parser modules.  Adding a new parser means updating this file only — no
changes required in the router.
"""
from parsers import BaseParser
from parsers.arp_output import ArpParser
from parsers.authorized_keys import AuthorizedKeysParser
from parsers.auth_log import AuthLogParser
from parsers.bash_history import BashHistoryParser
from parsers.docker_ps import DockerPsParser
from parsers.env_output import EnvOutputParser
from parsers.etc_hosts import EtcHostsParser
from parsers.ip_addr import IpAddrParser
from parsers.ip_neigh import IpNeighParser
from parsers.ip_route import IpRouteParser
from parsers.iptables import IptablesParser
from parsers.known_hosts import KnownHostsParser
from parsers.lastlog import LastlogParser
from parsers.last_output import LastOutputParser
from parsers.shell_rc import ShellRcParser
from parsers.zsh_history import ZshHistoryParser
from parsers.fish_history import FishHistoryParser
from parsers.network_interfaces import NetworkInterfacesParser
from parsers.netplan import NetplanParser
from parsers.ifcfg import IfcfgParser
from parsers.netstat import NetstatParser
from parsers.nftables import NftablesParser
from parsers.nmap_xml import NmapXmlParser
from parsers.passwd import PasswdParser
from parsers.private_key import PrivateKeyParser
from parsers.ps_output import PsOutputParser
from parsers.shadow import ShadowParser
from parsers.ss_output import SsOutputParser
from parsers.ssh_config import SshConfigParser
from parsers.sshd_config import SshdConfigParser
from parsers.sudoers import SudoersParser
from parsers.wtmp import WtmpParser

PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    "authorized_keys": AuthorizedKeysParser,
    "known_hosts": KnownHostsParser,
    "ssh_config": SshConfigParser,
    "private_key": PrivateKeyParser,
    "public_key": AuthorizedKeysParser,  # lone public key → same parser
    "auth_log": AuthLogParser,
    # RHEL/CentOS log aliases — same syslog/sshd format as auth.log
    "secure": AuthLogParser,
    "syslog": AuthLogParser,
    "messages": AuthLogParser,
    "wtmp": WtmpParser,
    "lastlog": LastlogParser,
    "last_output": LastOutputParser,
    "bashrc": ShellRcParser,
    "zshrc": ShellRcParser,
    "zsh_history": ZshHistoryParser,
    "fish_history": FishHistoryParser,
    "network_interfaces": NetworkInterfacesParser,
    "netplan": NetplanParser,
    "ifcfg": IfcfgParser,
    "bash_history": BashHistoryParser,
    "passwd": PasswdParser,
    "nmap_xml": NmapXmlParser,
    "shadow": ShadowParser,
    "sshd_config": SshdConfigParser,
    "etc_hosts": EtcHostsParser,
    "sudoers": SudoersParser,
    "ip_addr": IpAddrParser,
    "ip_route": IpRouteParser,
    "ip_neigh": IpNeighParser,
    "arp": ArpParser,
    "netstat": NetstatParser,
    "ss_output": SsOutputParser,
    "iptables": IptablesParser,
    "nftables": NftablesParser,
    "ps_output": PsOutputParser,
    "env_output": EnvOutputParser,
    "docker_ps": DockerPsParser,
}
