# Real Example Files — Sources

Reference samples for every parser Lockpick has or will have. Downloaded from public
repositories; all files retain the original content and licenses of their source
projects (mostly MIT, Apache 2.0, or CC0-equivalent). This directory is gitignored
(via `.gitignore`) because it's operational reference material, not tracked history.

Organized by `file_type` (matching `backend/parsers/registry.py` keys). Empty
subdirs at the bottom are parsers where I couldn't find public real samples.

---

## Currently-implemented parsers

### `auth_log/` — 5 files
- `auth.log` — original user-provided sample (pre-existing)
- `loghub_linux_2k.log` — logpai/loghub `Linux/Linux_2k.log` (2,000-line anonymized Linux auth corpus)
- `loghub_openssh_2k.log` — logpai/loghub `OpenSSH/OpenSSH_2k.log` (sshd-focused)
- `lastlog_audit_compromised` — franckferman/LastLog-Audit `samples/compromised.auth.log` (realistic red-team scenario)
- `masterparser_example` — securityjoes/MasterParser `01-Logs/MasterParser-Example-auth.log`

### `authorized_keys/` — 2 files
- `authorized_keys` — original (pre-existing)
- `otkrsk_multi_keys` — gist/otkrsk/b0ffd4018e8a79b9010c461af298471e

### `bash_history/` — 0 files
Couldn't find public real samples. Most `.bash_history` files contain private
commands and are gitignored in dotfiles repos. Recommend synthesizing or skipping.

### `etc_hosts/` — 1 file
- `centos_hosts` — original (pre-existing)

### `known_hosts/` — 1 file
- `known_hosts` — original (pre-existing)

### `nmap_xml/` — 4 files
- `nmap_example.xml` — original (pre-existing)
- `nmap_official_example` — nmap/nmap `zenmap/radialnet/share/sample/nmap_example.xml`
- `defectdojo_v7_12` — DefectDojo/sample-scan-files `nmap/nmap_output_v7.12.xml`
- `mozilla_minion_v6_40` — mozilla/minion-nmap-plugin `etc/sample-nmap-output.xml`

### `passwd/` — 1 file
- `endlessm_base_passwd_master` — endlessm/base-passwd `passwd.master` (Debian minimal default passwd)

### `private_key/` — 14 files
- `id_rsa`, `dss_key` — original (pre-existing; non-production keys)
- 12 paramiko test keys covering RSA / ECDSA (256/384/521) / Ed25519 / Ed448 variants, including password-encrypted, funky-padding, and `blank_rsa` edge cases. From paramiko/paramiko `tests/` and `tests/_support/`.

### `public_key/` — 6 files
- `id_rsa.pub`, `dss_key.pub` — original (pre-existing)
- `paramiko_test_rsa_pub`, `paramiko_ecdsa_256_cert`, `paramiko_ed25519_cert`, `paramiko_rsa_cert` — paramiko/paramiko tests (pub keys + cert keys)

### `shadow/` — 1 file
- `shadow` — original (pre-existing)

### `ssh_config/` — 20 files
- Pre-existing: `config`, `ssh-config-basic`, `ssh-config-patterns`, `ssh-config-proxy`
- `openssh_portable_default` — openssh/openssh-portable `ssh_config`
- `jc_generic_ssh_config{1..5}` — kellyjonbrazil/jc `tests/fixtures/generic/ssh_config[1-5]`
- 10 paramiko config edge-case fixtures (`basic`, `canon`, `match-all`, `match-exec`, `match-host-glob`, `match-host-glob-list`, `match-host-negated`, `match-localuser`, `hostname-tokenized`, `invalid`) — paramiko/paramiko `tests/configs/`

### `sshd_config/` — 4 files
- `openssh_portable_default.conf` — openssh/openssh-portable `sshd_config` (upstream default)
- `jc_generic_sshd_config_raw` — kellyjonbrazil/jc `tests/fixtures/generic/sshd_config`
- `jc_generic_sshd_T`, `jc_generic_sshd_T_2` — kellyjonbrazil/jc `generic/sshd-T.out` (output of `sshd -T`, a config-dump variant)

### `sudoers/` — 6 files
- `sudoers` — original (pre-existing)
- `official_sudo_project_example` — sudo-project/sudo `examples/sudoers.in` (upstream annotated example)
- `alitoufighi_ubuntu_default` — gist/alitoufighi/679304d9585304075ba1ad93f80cce0e (Ubuntu 18.04/20.04 default)
- `keith_macos_14_default` — gist/keith/9061156 (macOS 14.2.1 default)
- `kapb14_snippets` — gist/kapb14/802537c6a4c74f8ee1fa4e673af8847d (config snippets)
- `willsheppard_cheatsheet` — gist/willsheppard/f5ec8609a971e6c76f43c6a575c44d5d

### `wtmp/` — 1 file (binary)
- `compromised.wtmp` — franckferman/LastLog-Audit `samples/compromised.wtmp`

---

## Phase 17 — System file parsers

### `secure/` — 2 symlinks
RHEL/CentOS auth log — format-identical to `auth_log/` per AGENT.md Phase 17
(parser is a pure alias). Directory contains symlinks to `../auth_log/` files.

### `syslog/` — 2 files
- `loghub_linux_2k.log` — logpai/loghub `Linux/Linux_2k.log`
- `loghub_mac_2k.log` — logpai/loghub `Mac/Mac_2k.log`

### `messages/` — 1 file
- `loghub_thunderbird_2k.log` — logpai/loghub `Thunderbird/Thunderbird_2k.log`

### `lastlog/` — 9 files (all binary)
All from franckferman/LastLog-Audit `samples/`: `apt_cozy_bear`, `apt_lazarus`,
`brute_force`, `clean_server`, `compromised`, `insider_threat`,
`pentest_engagement`, `supply_chain`, `timestomped`.

### `last_output/` — 11 files (mostly from kellyjonbrazil/jc test fixtures)
- `jc_centos_last`, `jc_centos_last_crash`, `jc_centos_last_wF`, `jc_centos_last_wixF`, `jc_centos_lastb`
- `jc_ubuntu_last`, `jc_ubuntu_last_w`, `jc_ubuntu_lastb`, `jc_ubuntu2004_last_F`
- `jc_fedora32_last`
- `jonathanmorley_linux_commands` — gist/jonathanmorley/9876546 (Linux Commands cheatsheet)

### `zsh_history/` — 1 file
- `goyalankit_bash_to_zsh` — gist/goyalankit/a1c88bfc69107f93cda1 (bash→zsh history conversion snippets; short)

### `fish_history/` — 1 file
- `flawless13_fish_config` — Flawless13/fish-config `fish_history` (real fish history, 92KB)

### `bashrc/` — 6 files
All from dotfile repos: helmuthdu, tanghaibao, sporkmonger, miguelmota, gist/rchowe/1727301, gist/KaMeHb-UA/7b12035f29dad630f13a63a3dd72d183.

### `zshrc/` — 4 files
From dotfile repos: driesvints, wookayin, olivernn, ryanb.

### `network_interfaces/` — 3 files
- `fullmetalbrackets_static` — gist/fullmetalbrackets/4cc132571a2663c481b7c197d3681c78
- `sebw_debian_example` — gist/sebw/6018342
- `und3fined_sample` — gist/und3fined/e3b7eb511703ab7788dc15ae08254a7c

### `netplan/` — 8 files
All from canonical/netplan upstream `examples/`: `bridge`, `vlan`, `bonding`, `static`, `dhcp`, `wireless`, `modem`, `vrf`.

### `ifcfg/` — 3 files
- `coffman21_eth0` — gist/coffman21/a8df8d4667de3cb91d5cd86ce3ee0c52
- `rafaeltuelho_rhel7_static` — gist/rafaeltuelho/791d7838a9ccca8541d2
- `mjf_rhel_memos` — gist/mjf/8f6cdb6113316280e01c2b44ea8a80d0

---

## Phase 18 — Command output parsers

Most of these come from kellyjonbrazil/jc (`tests/fixtures/`), a CLI-output-to-JSON
parser library that maintains clean real-command-output fixtures per distro.

### `ip_addr/` — 2 files
- `jc_ubuntu_ifconfig`, `jc_centos_ifconfig` — AGENT.md Phase 18 says the `ip_addr`
  parser accepts `ip addr show` OR `ifconfig -a`. These are the `ifconfig` variant.

### `ip_route/` — 5 files (jc)
`jc_ubuntu_ip_route`, `jc_centos_ip_route`, `jc_ubuntu_route`, `jc_ubuntu_route_vn`,
plus `yuriskinfo_cheatsheet`.

### `ip_neigh/` — 0 files
jc doesn't have `ip_neigh` fixtures; couldn't find raw samples publicly.

### `arp/` — 5 files (jc)
`jc_ubuntu_arp`, `jc_ubuntu_arp_a`, `jc_ubuntu_arp_v`, `jc_centos_arp_a`, `jc_centos_arp_v`.

### `netstat/` — 11 files (jc)
Ubuntu 18.04 + generic: plain, `-l`, `-p`, `-rne`, `-sudo-aeep`, `-sudo-lnp`, plus generic `no-state`, `old`.

### `ss_output/` — 3 files (jc)
`jc_ubuntu_ss_a`, `jc_ubuntu_ss_tulpen`, `jc_generic_ss_wide`.

### `iptables/` — 10 files
- From jc centos-7.7: `filter`, `filter-nv`, `nat`, `mangle`, `raw`
- From jc generic: `no_jump`
- From gists: polster, hlissner, DominicBreuker, pirafrank (rule files, not command output)

### `nftables/` — 3 files
- `arch_example` — archlinux svntogit `nftables.conf`
- `gaelanlloyd_example` — gist/gaelanlloyd/0677759fd4dc0f58e1e7449784bb8903
- `yoramvandevelde_init_rules` — yoramvandevelde/nftables-example

### `ps_output/` — 4 files
- `jc_ubuntu_ps_axu`, `jc_ubuntu_ps_ef`, `jc_centos_ps_axu`
- `cahna_ps_aux_parse` — gist/cahna/43a1a3ff4d075bcd71f9d7120037a501 (short)

### `env_output/` — 3 files (jc)
`jc_centos_env`, `jc_ubuntu_env`, `jc_generic_multiline`.

### `docker_ps/` — 4 files
All from gists: jimklo, sudo-bmitch, deanpeterson, ipedrazas.

### `docker_network/` — 1 file
- `docker_cli_docs_reference.md` — docker/cli `docs/reference/commandline/network_inspect.md` (official Docker CLI docs containing multiple verbatim `docker network inspect` JSON outputs in fenced code blocks)

### `ip_neigh/` — 1 file
- `wsl_live_capture.out` — live capture of `ip neigh show` from this WSL2 environment (RFC1918 only: Docker bridge + WSL gateway; no hostnames, no public IPs)

### `kubectl_pods/` — 2 files
- `so0k_kubectl_output` — gist/so0k/42313dbb3b547a0f51a547bb968696ba
- `devops_school_kubectl_ref` — gist/devops-school/98e78b62b0cca22158aef9ef90daa6af

---

## Phase 19 — Credential file parsers

### `netrc/` — 3 files
- `tpope_sample` — gist/tpope/4247721
- `technoweenie_github` — gist/technoweenie/1072829
- `sahilsk_git` — gist/sahilsk/ce21c39a6c2dbc2cd984

### `pgpass/` — 3 files
- `sabman_sample` — gist/sabman/978352
- `Fmstrat_aliased` — gist/Fmstrat/ea6287a6d60e3e5f6c73e3bdd2f62331
- `vielhuber_sample` — gist/vielhuber/96eefdb3aff327bdf8230d753aaee1e1

### `mysql_config/` — 5 files
- `oinume_mycnf` — gist/oinume/fc9b72bd8b14ab07e94c
- `fevangelou_optimized` — gist/fevangelou/fb72f36bbe333e059b66
- `juliandunn_container_default` — gist/juliandunn/7efc161ee2bec4801422d90bab24ad12
- `byllc_mariadb` — gist/byllc/8871383
- `rubo77_debian_mysql55` — gist/rubo77/64f64a26bdf9c677ca79

### `aws_credentials/` — 3 files
- `mrsarm_multi_profile` — gist/mrsarm/5169b18d47edd4539695964e2e695a18
- `wjimenez5271_sample` — gist/wjimenez5271/defeede8eb4a63afc9d8
- `wyllie_parse_sample` — gist/wyllie/c99a0ccba64af5e3e6ca901c7a2c9e5d

### `aws_config/` — 2 files
- `ohaval_multi_env` — gist/ohaval/1719fb6fb0e206469960c34699ef6065 (multi-environment profiles)
- `awsdocs_user_guide_examples.md` — awsdocs/aws-cli-user-guide `doc_source/cli-configure-files.md` (official AWS docs markdown with many inline config examples)

### `gcloud_credentials/` — 1 file
- `dims_gcp_quick_start` — gist/dims/19fff66f27445c5c1f0e0195e203afef

### `kubeconfig/` — 3 files
- `devops_school_skeleton` — gist/devops-school/f8956d4ee208b2519b095ad631eac7a0
- `innovia_sa_config` — gist/innovia/fbba8259042f71db98ea8d4ad19bd708
- `tdihp_aks_config` — gist/tdihp/95716ed2ecef99582af06a50f71d2631

### `boto/` — 0 files
Docs show inline format, no raw samples. Would need synthesis.

### `env_file/` — 1 file
- `rapidpages_env_example` — rapidpages/rapidpages `.env.example`

### `docker_config/` — 2 files
- `piersharding_auth` — gist/piersharding/44cbd66f8aeebfd5abd02fb9c8f753d7
- `browol_manual_gen` — gist/browol/6f256b4d1e880cb5692f16acab0e870f

### `git_credentials/` — 3 files
- `klo2k_store` — gist/klo2k/dfcb0fad1038c97de1c1ae42c0bfea17
- `richardbronosky_sample` — gist/RichardBronosky/9ab50abb8698e02341629db21e5fa6bf
- `dan_hart_store` — gist/dan-hart/c3553b5e8514faef440041d34cf95a78 (short)

### `rclone_config/` — 1 file
- `fotile96_sample` — gist/fotile96/1b0a27b7fa8059a6830b97f9368d377f

---

## Remaining gaps (3 dirs still empty after exhaustive search)

| Parser | Why it's hard | Suggestion |
|---|---|---|
| `bash_history` | Private by nature, gitignored everywhere; no public DFIR corpus publishes them as raw files | Capture from a live host or honeypot, or synthesize from real SSH command patterns |
| `boto` | Only inline doc examples exist — format is rare enough that nobody publishes raw `~/.boto` files | Synthesize from the [official boto config tutorial](https://boto.cloudhackers.com/en/latest/boto_config_tut.html) |

Both `ip_neigh` and the two that are hard to find as raw files are essentially captures away — running the commands on any Linux box produces a real sample. Let me know if you want me to do that here.

---

## Primary upstream sources (attribution)

- [kellyjonbrazil/jc](https://github.com/kellyjonbrazil/jc) — MIT — ~55 test fixtures across distros
- [logpai/loghub](https://github.com/logpai/loghub) — CC-BY-NC-SA-2.0 — anonymized log corpus
- [franckferman/LastLog-Audit](https://github.com/franckferman/LastLog-Audit) — binary lastlog + wtmp samples
- [securityjoes/MasterParser](https://github.com/securityjoes/MasterParser) — DFIR auth.log sample
- [openssh/openssh-portable](https://github.com/openssh/openssh-portable) — BSD — upstream ssh_config/sshd_config defaults
- [canonical/netplan](https://github.com/canonical/netplan) — GPL-3.0 — network YAML examples
- [sudo-project/sudo](https://github.com/sudo-project/sudo) — ISC — upstream sudoers example
- [endlessm/base-passwd](https://github.com/endlessm/base-passwd) — GPL-2.0 — Debian passwd.master
- Various GitHub gists — per-file attribution above
