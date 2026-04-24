# Real Example Files — Sources

Reference samples for every parser Lockpick has or will have. Downloaded from public
repositories; all files retain the original content and licenses of their source
projects (mostly MIT, Apache 2.0, or CC0-equivalent).

Organized by `file_type` (matching `backend/parsers/registry.py` keys).

---

## Currently-implemented parsers

### `auth_log/` — 5 files
- `auth.log` — original user-provided sample (pre-existing)
- `loghub_linux_2k.log` — logpai/loghub `Linux/Linux_2k.log` (2,000-line anonymized Linux auth corpus)
- `loghub_openssh_2k.log` — logpai/loghub `OpenSSH/OpenSSH_2k.log` (sshd-focused)
- `lastlog_audit_compromised` — franckferman/LastLog-Audit `samples/compromised.auth.log` (realistic red-team scenario)
- `masterparser_example` — securityjoes/MasterParser `01-Logs/MasterParser-Example-auth.log`

### `authorized_keys/` — 3 files
- `authorized_keys` — original (pre-existing)
- `saltstack_integration_command_prefix` — saltstack/salt `tests/integration/files/ssh/authorized_keys` (single entry with `command="..."` option prefix — important edge case)
- `saltstack_git_pillar_user` — saltstack/salt `tests/integration/files/file/base/git_pillar/ssh/user/files/authorized_keys`

### `bash_history/` — 2 files
- `jc_ubuntu_18_04_history`, `jc_centos_7_7_history` — kellyjonbrazil/jc `tests/fixtures/{ubuntu-18.04,centos-7.7}/history.out`
  > **Note:** these are the OUTPUT of the `history` shell builtin (numbered lines), not raw `~/.bash_history` files. The parser's regex tolerates both formats. Real `.bash_history` files are private by convention and rarely committed publicly.

### `etc_hosts/` — 5 files
- `centos_hosts` — original (pre-existing)
- `jc_ubuntu_18_04_hosts`, `jc_centos_7_7_hosts` — kellyjonbrazil/jc `tests/fixtures/{ubuntu-18.04,centos-7.7}/hosts.out`
- `saltstack_integration`, `saltstack_modules` — saltstack/salt `tests/integration/files/hosts` + `tests/integration/modules/files/hosts`

### `known_hosts/` — 4 files
- `known_hosts` — original (pre-existing)
- `openssh_portable_hostkeys_unittest` — openssh/openssh-portable `regress/unittests/hostkeys/testdata/known_hosts`
- `ansible_existing_known_hosts` — ansible/ansible `test/integration/targets/known_hosts/files/existing_known_hosts` (mix of plain, `|1|`-hashed, `@cert-authority`, and multi-key-type entries)
- `saltstack_integration` — saltstack/salt `tests/integration/files/ssh/known_hosts` (hashed + GitHub ecdsa/ed25519 real keys)

### `nmap_xml/` — 5 files
- `nmap_example.xml` — original (pre-existing)
- `nmap_official_example` — nmap/nmap `zenmap/radialnet/share/sample/nmap_example.xml`
- `defectdojo_v7_12` — DefectDojo/sample-scan-files `nmap/nmap_output_v7.12.xml`
- `defectdojo_v6_40` — DefectDojo/sample-scan-files `nmap/nmap_v6.40.xml`
- `mozilla_minion_v6_40` — mozilla/minion-nmap-plugin `etc/sample-nmap-output.xml`

### `passwd/` — 5 files
- `endlessm_base_passwd_master` — endlessm/base-passwd `passwd.master` (Debian minimal default passwd)
- `jc_ubuntu_18_04_passwd`, `jc_centos_7_7_passwd`, `jc_osx_10_14_6_passwd` — kellyjonbrazil/jc `tests/fixtures/*/passwd.out`
- `cowrie_honeyfs_passwd` — cowrie/cowrie `honeyfs/etc/passwd` (honeypot fake passwd served to attackers)

### `private_key/` — 22 files
- `id_rsa`, `dss_key` — original (pre-existing; non-production keys)
- 12 paramiko test keys from round 1: RSA / ECDSA (256/384/521) / Ed25519 / Ed448, including password-encrypted, funky-padding, and `blank_rsa` edge cases
- Round 2 additions from paramiko/paramiko: `paramiko_test_rsa_openssh_nopad`, `paramiko_test_ecdsa_password_384`, `paramiko_test_ecdsa_password_521`, `paramiko_ed25519_funky_padding_password`, `paramiko_badhash_key1_ed25519`, `paramiko_badhash_key2_ed25519` (corrupted-hash edge cases), `paramiko_support_rsa_lonely`, `paramiko_demos_user_rsa`

### `public_key/` — 9 files
- `id_rsa.pub`, `dss_key.pub` — original (pre-existing)
- Round 1: `paramiko_test_rsa_pub`, `paramiko_ecdsa_256_cert`, `paramiko_ed25519_cert`, `paramiko_rsa_cert`
- Round 2: `paramiko_support_rsa_cert`, `paramiko_support_rsa_missing_cert` (cert-pub-without-matching-key edge case), `paramiko_demos_user_rsa_pub`

### `shadow/` — 4 files
- `shadow` — original (pre-existing)
- `jc_ubuntu_18_04_shadow`, `jc_centos_7_7_shadow` — kellyjonbrazil/jc `tests/fixtures/*/shadow.out`
- `cowrie_honeyfs_shadow` — cowrie/cowrie `honeyfs/etc/shadow` (hashes are fake honeypot bait)

### `ssh_config/` — 20 files
- Pre-existing: `config`, `ssh-config-basic`, `ssh-config-patterns`, `ssh-config-proxy`
- `openssh_portable_default` — openssh/openssh-portable `ssh_config`
- `jc_generic_ssh_config{1..5}` — kellyjonbrazil/jc `tests/fixtures/generic/ssh_config[1-5]`
- 10 paramiko config edge-case fixtures (`basic`, `canon`, `match-all`, `match-exec`, `match-host-glob`, `match-host-glob-list`, `match-host-negated`, `match-localuser`, `hostname-tokenized`, `invalid`) — paramiko/paramiko `tests/configs/`

### `sshd_config/` — 7 files
- `openssh_portable_default.conf` — openssh/openssh-portable `sshd_config` (upstream default)
- `jc_generic_sshd_config_raw` — kellyjonbrazil/jc `tests/fixtures/generic/sshd_config`
- `jc_generic_sshd_T`, `jc_generic_sshd_T_2` — kellyjonbrazil/jc `generic/sshd-T.out` (output of `sshd -T`, a config-dump variant)
- `ansible_blockinfile_openbsd_default` — ansible/ansible `test/integration/targets/blockinfile/files/sshd_config` (OpenBSD 1.100 upstream default)
- `saltstack_debian_pkg_generated` — saltstack/salt `tests/integration/files/conf/_ssh/sshd_config` (Debian package-generated variant)
- `saltstack_git_pillar_minimal` — saltstack/salt `tests/integration/files/file/base/git_pillar/ssh/server/files/sshd_config` (9-line minimal config)

### `sudoers/` — 5 files
- `sudoers` — original (pre-existing)
- `official_sudo_project_example` — sudo-project/sudo `examples/sudoers.in` (upstream annotated example)
- `alitoufighi_ubuntu_default` — gist/alitoufighi/679304d9585304075ba1ad93f80cce0e (Ubuntu 18.04/20.04 default)
- `keith_macos_14_default` — gist/keith/9061156 (macOS 14.2.1 default)
- `kapb14_snippets` — gist/kapb14/802537c6a4c74f8ee1fa4e673af8847d (config snippets)

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

### `last_output/` — 14 files (all from kellyjonbrazil/jc test fixtures)
- `jc_centos_last`, `jc_centos_last_crash`, `jc_centos_last_wF`, `jc_centos_last_wixF`, `jc_centos_last_w`, `jc_centos_lastb`
- `jc_ubuntu_last`, `jc_ubuntu_last_w`, `jc_ubuntu_last_w2`, `jc_ubuntu_lastb`, `jc_ubuntu2004_last_F`
- `jc_fedora32_last`, `jc_osx_1014_last`, `jc_freebsd12_last` — macOS + FreeBSD variants
  > Round 2 audit removed `jonathanmorley_linux_commands` — Linux commands cheatsheet, not `last`/`lastb` output.

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

### `ip_addr/` — 11 files
- `jc_ubuntu_ifconfig`, `jc_centos_ifconfig` — AGENT.md Phase 18 says the `ip_addr`
  parser accepts `ip addr show` OR `ifconfig -a`. These are the `ifconfig` variant.
- `jc_ubuntu_1604_ifconfig` — kellyjonbrazil/jc `ubuntu-16.04/ifconfig.out`
- `jc_osx_1014_ifconfig`, `jc_osx_1014_ifconfig2`, `jc_osx_1011_ifconfig`, `jc_osx_1011_ifconfig2` — jc macOS variants
- `jc_freebsd12_ifconfig`, `jc_freebsd12_ifconfig2`, `jc_freebsd12_ifconfig3`, `jc_freebsd12_ifconfig4` — jc FreeBSD 12 (tests extra-field handling)

### `ip_route/` — 8 files (jc)
`jc_ubuntu_ip_route`, `jc_centos_ip_route`, `jc_ubuntu_route`, `jc_ubuntu_route_vn`,
`yuriskinfo_cheatsheet`, `jc_route_6_ipv6`, `jc_route_6_n_ipv6`, `jc_nixos_route_ee`
(IPv6 + `route -ee` variants).

### `ip_neigh/` — 0 files
jc doesn't have `ip_neigh` fixtures; couldn't find raw samples publicly.

### `arp/` — 12 files (jc)
Original 5 (`jc_ubuntu_arp*`, `jc_centos_arp*`) plus:
- `jc_aix71_arp_a`, `jc_freebsd12_arp_a`, `jc_centos8_arp_a` — non-Linux + newer distros
- `jc_osx_1014_arp_a`, `jc_osx_1014_arp_a2`, `jc_osx_1011_arp_a` — macOS format variants
- `jc_linux_proc_net_arp` — `/proc/net/arp` raw format

### `netstat/` — 24 files
Original 11 (ubuntu + generic) plus:
- `jc_centos_netstat`, `jc_centos_netstat_l`, `jc_centos_netstat_p` — CentOS 7.7 variants
- `jc_ubuntu_netstat_r`, `jc_ubuntu_netstat_rnee`, `jc_ubuntu_netstat_i` — more ubuntu flag variants
- `jc_osx_netstat`, `jc_osx_netstat_An`, `jc_osx_netstat_Abn`, `jc_osx_netstat_r`, `jc_osx_netstat_rnl`, `jc_osx_netstat_i` — macOS format variants (different column layout)
- `jc_fedora32_netstat` — Fedora 32 variant

### `ss_output/` — 4 files (jc)
`jc_ubuntu_ss_a`, `jc_ubuntu_ss_tulpen`, `jc_generic_ss_wide`, `jc_centos_ss_a`.

### `iptables/` — 13 files (jc only; tutorials removed)
- From jc centos-7.7: `filter`, `filter-nv`, `filter_line_numbers`, `nat`, `mangle`, `raw`
- From jc ubuntu-18.04: `filter`, `filter_nv`, `filter_line_numbers`, `mangle`, `nat`, `raw`
- From jc generic: `no_jump`
  > Round 2 audit removed 4 gist-sourced entries (`dominicbreuker_firewall` — markdown cheatsheet; `hlissner_default`, `polster_sample` — bash scripts; `pirafrank_basic` — shell command snippets). Only canonical `iptables-save` / `iptables -L` command output belongs here.

### `nftables/` — 8 files
- `arch_example` — archlinux svntogit `nftables.conf`
- `gaelanlloyd_example` — gist/gaelanlloyd/0677759fd4dc0f58e1e7449784bb8903
- `yoramvandevelde_init_rules` — yoramvandevelde/nftables-example
- `aborrero_ruleset`, `aborrero_filter_forward`, `aborrero_filter_input`, `aborrero_filter_output`, `aborrero_filter_sets` — aborrero/nftables-managed-with-git `nft_ruleset/` (split-file production-style ruleset)

### `ps_output/` — 9 files
- `jc_ubuntu_ps_axu`, `jc_ubuntu_ps_ef`, `jc_centos_ps_axu`, `jc_centos_ps_ef`
- `jc_osx_1014_ps_axu`, `jc_osx_1014_ps_ef`, `jc_osx_1011_ps_axu`, `jc_osx_1011_ps_ef` — macOS format variants
- `cahna_ps_aux_parse` — gist/cahna/43a1a3ff4d075bcd71f9d7120037a501 (short)

### `env_output/` — 3 files (jc)
`jc_centos_env`, `jc_ubuntu_env`, `jc_generic_multiline`.

### `docker_ps/` — 4 files
All from gists: jimklo, sudo-bmitch, deanpeterson, ipedrazas.

### `docker_network/` — 0 files (pending)
All entries from round 1/2 were removed: the docker CLI docs `.md` file was tutorial, and the `docker inspect CONTAINER` gists produced a different JSON shape than `docker network inspect NETWORK` (no `IPAM.Config`/`Containers` at the top level). No canonical `docker network inspect` fixtures located in public repos; Phase 18 parser will need custom samples.

### `kubectl_pods/` — 0 files (pending)
Both round-1 gist entries (`devops_school_kubectl_ref`, `so0k_kubectl_output`) were kubectl cheatsheets/tutorials — not actual `kubectl get pods` output. kubernetes/kubectl `testdata/` contains pod INPUT manifests for `apply`, not pod-list output. Phase 18 parser will need custom samples.

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

### `pgpass/` — 2 files
- `sabman_sample` — gist/sabman/978352
- `Fmstrat_aliased` — gist/Fmstrat/ea6287a6d60e3e5f6c73e3bdd2f62331
  > Round 2 audit removed `vielhuber_sample` — "best practice linux" tutorial with snippets, not a raw `.pgpass` file.

### `mysql_config/` — 5 files
- `oinume_mycnf` — gist/oinume/fc9b72bd8b14ab07e94c
- `fevangelou_optimized` — gist/fevangelou/fb72f36bbe333e059b66
- `juliandunn_container_default` — gist/juliandunn/7efc161ee2bec4801422d90bab24ad12
- `byllc_mariadb` — gist/byllc/8871383
- `rubo77_debian_mysql55` — gist/rubo77/64f64a26bdf9c677ca79

### `aws_credentials/` — 1 file
- `mrsarm_multi_profile` — gist/mrsarm/5169b18d47edd4539695964e2e695a18
  > Round 2 audit removed 2 non-canonical entries (`wjimenez5271_sample` — Python script; `wyllie_parse_sample` — bash script).

### `aws_config/` — 1 file
- `ohaval_multi_env` — gist/ohaval/1719fb6fb0e206469960c34699ef6065 (multi-environment profiles)
  > Round 2 audit removed `awsdocs_user_guide_examples.md` (official docs markdown, not a raw `~/.aws/config` file).

### `gcloud_credentials/` — 6 files (all from googleapis/google-auth-library-python `tests/data/`)
- `google_auth_authorized_user` — minimal canonical `authorized_user` JSON
- `google_auth_cloud_sdk` — real-shape `client_id` (googleusercontent.com format)
- `google_auth_cloud_sdk_with_quota` — with `quota_project_id` field
- `google_auth_with_rapt_token` — with `rapt_token`
- `google_auth_external_account` — `external_account` type (WIF)
- `google_auth_external_account_non_gdu` — non-GDU variant
  > Replaced round-1 `dims_gcp_quick_start` tutorial with google's own library test corpus.

### `kubeconfig/` — 1 file
- `devops_school_skeleton` — gist/devops-school/f8956d4ee208b2519b095ad631eac7a0 (canonical YAML with `apiVersion/clusters/contexts/users`)
  > Round 2 audit removed `innovia_sa_config` (bash script) and `tdihp_aks_config` (tutorial markdown).

### `boto/` — 2 files
- `garnaat_eucalyptus_credentials` — gist/garnaat/1284158 (Eucalyptus-flavored `[Credentials]` block)
- `kevinkarwaski_example` — gist/kevinkarwaski/1007405 (annotated `[Credentials]` + `[Boto]` reference config with proxy settings)

### `env_file/` — 2 files
- `rapidpages_env_example` — rapidpages/rapidpages `.env.example`
- `ansible_types_env` — ansible/ansible `test/integration/targets/config/files/types.env`

### `docker_config/` — 2 files
- `piersharding_auth` — gist/piersharding/44cbd66f8aeebfd5abd02fb9c8f753d7
- `browol_manual_gen` — gist/browol/6f256b4d1e880cb5692f16acab0e870f

### `git_credentials/` — 2 files
- `git_upstream_test_format_basic`, `git_upstream_test_format_store` — canonical `https://user:pass@host` format extracted from git/git `t/t0302-credential-store.sh` test suite.
  > Round 2 audit removed all 3 round-1 gist entries (`klo2k_store`, `richardbronosky_sample`, `dan_hart_store`) — all were tutorial markdown or one-line git config commands, not raw `~/.git-credentials` files.

### `rclone_config/` — 1 file
- `fotile96_sample` — gist/fotile96/1b0a27b7fa8059a6830b97f9368d377f (canonical `[remote]` INI)
  > Round 2 audit removed 3 markdown tutorials I added prematurely (`kelvinrr_config_session.md`, `magnetikonline_b2_cheatsheet.md`, `plembo_gdrive_backup.md`) — they contain rclone config in fenced blocks but the file format is markdown, not rclone.conf.

---

## Remaining thin dirs

| Parser | Count | Status |
|---|---|---|
| `ip_neigh` | 1 | public gists are tutorials, not captures |
| `fish_history` | 1 | pseudo-YAML format rarely committed; private by convention |
| `zsh_history` | 1 | same as fish; public gists are scripts that manipulate the file, not real histories |
| `wtmp` | 1 | binary format; only LastLog-Audit publishes raw `.wtmp` files publicly |
| `messages` | 1 | RHEL/CentOS variant of auth log; the `auth_log/` corpus transfers |
| `rclone_config` | 1 | canonical `rclone.conf` is rare publicly; only one clean sample located |
| `aws_config` | 1 | see above |
| `aws_credentials` | 1 | see above |
| `kubeconfig` | 1 | public kubeconfigs nearly always redacted or embedded in tutorials |
| `docker_network` | 0 | canonical `docker network inspect NETWORK` JSON not located in public repos |
| `kubectl_pods` | 0 | canonical `kubectl get pods` output not located in public repos |

These gaps are genuine — either the file is private by convention (history files, credentials) or the canonical command output isn't regularly committed as test fixtures.

---

## Primary upstream sources (attribution)

- [kellyjonbrazil/jc](https://github.com/kellyjonbrazil/jc) — MIT — ~110 test fixtures across distros (Ubuntu 16/18/20, CentOS 7/8, macOS 10.11/10.14, FreeBSD 12, AIX 7.1, Fedora 32, NixOS)
- [logpai/loghub](https://github.com/logpai/loghub) — CC-BY-NC-SA-2.0 — anonymized log corpus
- [franckferman/LastLog-Audit](https://github.com/franckferman/LastLog-Audit) — binary lastlog + wtmp samples
- [securityjoes/MasterParser](https://github.com/securityjoes/MasterParser) — DFIR auth.log sample
- [openssh/openssh-portable](https://github.com/openssh/openssh-portable) — BSD — upstream ssh_config/sshd_config defaults + unit-test `known_hosts`
- [paramiko/paramiko](https://github.com/paramiko/paramiko) — LGPL-2.1 — RSA/ECDSA/Ed25519/Ed448 private+public key fixtures, cert keys, corrupted-hash edge cases, ssh_config match-exec fixtures
- [ansible/ansible](https://github.com/ansible/ansible) — GPL-3.0 — `existing_known_hosts` (hashed + cert-authority entries), OpenBSD sshd_config, types.env
- [saltstack/salt](https://github.com/saltstack/salt) — Apache-2.0 — authorized_keys (with `command="..."` prefix), sshd_config (Debian pkg variant), known_hosts, hosts
- [cowrie/cowrie](https://github.com/cowrie/cowrie) — BSD — honeypot `honeyfs/etc/passwd` + `shadow` (fake but realistic)
- [canonical/netplan](https://github.com/canonical/netplan) — GPL-3.0 — network YAML examples
- [sudo-project/sudo](https://github.com/sudo-project/sudo) — ISC — upstream sudoers example
- [endlessm/base-passwd](https://github.com/endlessm/base-passwd) — GPL-2.0 — Debian passwd.master
- [aborrero/nftables-managed-with-git](https://github.com/aborrero/nftables-managed-with-git) — split-file nftables ruleset
- [DefectDojo/sample-scan-files](https://github.com/DefectDojo/sample-scan-files) — Apache-2.0 — nmap XML v6.40 + v7.12
- [googleapis/google-auth-library-python](https://github.com/googleapis/google-auth-library-python) — Apache-2.0 — `application_default_credentials.json` test fixtures
- [git/git](https://github.com/git/git) — GPL-2.0 — `.git-credentials` canonical format (from `t/t0302-credential-store.sh`)
- Various GitHub gists — per-file attribution above
