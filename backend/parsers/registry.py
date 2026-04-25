"""Maps file_type strings to parser classes.

Centralises the parser registry so upload.py is decoupled from individual
parser modules.  Adding a new parser means updating this file only — no
changes required in the router.
"""
from parsers import BaseParser
from parsers.authorized_keys import AuthorizedKeysParser
from parsers.auth_log import AuthLogParser
from parsers.aws_config import AwsConfigParser
from parsers.aws_credentials import AwsCredentialsParser
from parsers.bash_history import BashHistoryParser
from parsers.boto import BotoParser
from parsers.docker_config import DockerConfigParser
from parsers.env_file import EnvFileParser
from parsers.etc_hosts import EtcHostsParser
from parsers.gcloud_credentials import GcloudCredentialsParser
from parsers.known_hosts import KnownHostsParser
from parsers.kubeconfig import KubeconfigParser
from parsers.mysql_config import MysqlConfigParser
from parsers.netrc import NetrcParser
from parsers.nmap_xml import NmapXmlParser
from parsers.passwd import PasswdParser
from parsers.pgpass import PgpassParser
from parsers.private_key import PrivateKeyParser
from parsers.shadow import ShadowParser
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
    "wtmp": WtmpParser,
    "bash_history": BashHistoryParser,
    "passwd": PasswdParser,
    "nmap_xml": NmapXmlParser,
    "shadow": ShadowParser,
    "sshd_config": SshdConfigParser,
    "etc_hosts": EtcHostsParser,
    "sudoers": SudoersParser,
    "netrc": NetrcParser,
    "pgpass": PgpassParser,
    "mysql_config": MysqlConfigParser,
    "aws_config": AwsConfigParser,
    "aws_credentials": AwsCredentialsParser,
    "boto": BotoParser,
    "gcloud_credentials": GcloudCredentialsParser,
    "kubeconfig": KubeconfigParser,
    "env_file": EnvFileParser,
    "docker_config": DockerConfigParser,
}
