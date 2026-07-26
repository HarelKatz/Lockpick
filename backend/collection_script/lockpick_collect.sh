#!/usr/bin/env bash
# lockpick_collect.sh — gather parseable SSH / credential / log evidence into a tarball.
#
# Usage:
#   ./lockpick_collect.sh                        # writes to $PWD
#   OUT_DIR=/tmp ./lockpick_collect.sh           # writes to /tmp
#
# Runs as the invoking user. No sudo, no network, no side effects on the
# target beyond a short-lived staging dir under $TMPDIR. Re-running and
# re-importing produces no duplicates — Lockpick dedups by record
# (credential fingerprint, credential-link composite key).
#
# Filename convention inside the tarball: <file_type>__<username>.<ext>
# Optional manifest.json records original paths and stderr presence.
#
# Exits 0 even if some files could not be read — missing/unreadable files
# surface as warnings on import. Only hard failures (no tar, no gzip,
# unwritable OUT_DIR) cause a non-zero exit.

set -u

# ── 0. Pre-flight ─────────────────────────────────────────────────────────────
for bin in tar gzip; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        printf 'lockpick_collect: %s not found in PATH\n' "$bin" >&2
        exit 1
    fi
done

OUT_DIR="${OUT_DIR:-$PWD}"
if [ ! -d "$OUT_DIR" ] || [ ! -w "$OUT_DIR" ]; then
    printf 'lockpick_collect: OUT_DIR %s missing or not writable\n' "$OUT_DIR" >&2
    exit 1
fi

STAGING="$(mktemp -d -t lockpick.XXXXXX 2>/dev/null || mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

HOSTNAME_S="$(hostname -s 2>/dev/null || echo unknown)"
GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
INVOKING_USER="$(id -un 2>/dev/null || echo unknown)"
OUTFILE="$OUT_DIR/lockpick_${HOSTNAME_S}_$(date -u +%Y%m%dT%H%M%SZ).tar.gz"

# Entry side-file — one line per gathered artifact, separated by ASCII Unit
# Separator (0x1F). Bash `read` collapses consecutive whitespace IFS chars
# (tabs included), which corrupts rows where username is empty; 0x1F is
# non-whitespace so `read` preserves empty fields. Columns:
#   file_type ␟ username ␟ source_path ␟ archived_as ␟ stderr_present
ENTRIES_FILE="$STAGING/.entries"
US=$'\x1f'
: > "$ENTRIES_FILE"

# ── 1. Gathering helpers ──────────────────────────────────────────────────────
# gather_file SRC_PATH FILE_TYPE USERNAME [EXT]
#   Copies SRC_PATH to $STAGING/<file_type>__<username>.<ext> (default ext: txt).
#   If the source is unreadable or missing, stderr goes to a .err sibling.
#   Truly absent files are silently skipped (no manifest entry).
gather_file() {
    local src="$1" file_type="$2" username="$3" ext="${4:-txt}"
    [ -e "$src" ] || return 0
    local archived="${file_type}__${username}.${ext}"
    local target="$STAGING/$archived"
    local err="$STAGING/${archived}.err"
    if cp -- "$src" "$target" 2>"$err"; then
        if [ -s "$err" ]; then
            record_entry "$file_type" "$username" "$src" "$archived" true
        else
            rm -f "$err"
            record_entry "$file_type" "$username" "$src" "$archived" false
        fi
    else
        # cp failed (typically EACCES) — keep the .err, drop the partial target.
        rm -f "$target"
        record_entry "$file_type" "$username" "$src" "${archived}.err" true
    fi
}

# gather_cmd FILE_TYPE USERNAME CMD [ARGS...]
#   Runs the command, captures stdout to <file_type>__<username>.out and
#   stderr to .err sibling. Missing commands silently skipped.
gather_cmd() {
    local file_type="$1" username="$2"
    shift 2
    command -v "$1" >/dev/null 2>&1 || return 0
    local archived="${file_type}__${username}.out"
    local target="$STAGING/$archived"
    local err="$STAGING/${archived}.err"
    "$@" >"$target" 2>"$err" || true
    local stderr_present=false
    if [ -s "$err" ]; then
        stderr_present=true
    else
        rm -f "$err"
    fi
    if [ -s "$target" ] || [ "$stderr_present" = true ]; then
        record_entry "$file_type" "$username" "(command: $*)" "$archived" "$stderr_present"
    else
        rm -f "$target"
    fi
}

# record_entry FILE_TYPE USERNAME SRC ARCHIVED STDERR_PRESENT
#   ASCII-US-separated side-file; converted to JSON at the end.
record_entry() {
    printf '%s%s%s%s%s%s%s%s%s\n' "$1" "$US" "$2" "$US" "$3" "$US" "$4" "$US" "$5" >> "$ENTRIES_FILE"
}

# ── 2. Per-user artifacts ─────────────────────────────────────────────────────
gather_for_user() {
    local home="$1"
    local user
    user="$(basename -- "$home")"

    # SSH
    gather_file "$home/.ssh/authorized_keys"  authorized_keys "$user"
    gather_file "$home/.ssh/known_hosts"      known_hosts     "$user"
    gather_file "$home/.ssh/config"           ssh_config      "$user"
    local k
    for k in id_rsa id_dsa id_ecdsa id_ed25519 id_ecdsa_sk id_ed25519_sk; do
        gather_file "$home/.ssh/$k"           private_key     "${user}_${k}"
    done
    # public keys: copy any *.pub under .ssh/
    if [ -d "$home/.ssh" ]; then
        local pub
        for pub in "$home"/.ssh/*.pub; do
            [ -e "$pub" ] || continue
            local base
            base="$(basename -- "$pub" .pub)"
            gather_file "$pub" public_key "${user}_${base}" pub
        done
    fi

    # Shell histories + rc files
    gather_file "$home/.bash_history"         bash_history    "$user"
    gather_file "$home/.zsh_history"          zsh_history     "$user"
    gather_file "$home/.local/share/fish/fish_history" fish_history "$user"
    gather_file "$home/.bashrc"               bashrc          "$user"
    gather_file "$home/.zshrc"                zshrc           "$user"

    # Credential / config files
    gather_file "$home/.netrc"                netrc           "$user"
    gather_file "$home/.pgpass"               pgpass          "$user"
    gather_file "$home/.my.cnf"               mysql_config    "$user"
    gather_file "$home/.aws/credentials"      aws_credentials "$user"
    gather_file "$home/.aws/config"           aws_config      "$user"
    gather_file "$home/.config/gcloud/application_default_credentials.json" gcloud_credentials "$user" json
    gather_file "$home/.kube/config"          kubeconfig      "$user"
    gather_file "$home/.git-credentials"      git_credentials "$user"
    gather_file "$home/.docker/config.json"   docker_config   "$user" json
    gather_file "$home/.config/rclone/rclone.conf" rclone_config "$user"
    gather_file "$home/.boto"                 boto            "$user"
}

# Iterate /root and /home/*
gather_for_user "/root"
if [ -d /home ]; then
    for home in /home/*; do
        [ -d "$home" ] || continue
        gather_for_user "$home"
    done
fi

# ── 3. System-wide files ──────────────────────────────────────────────────────
gather_file /etc/passwd          passwd        ""
gather_file /etc/shadow          shadow        ""
gather_file /etc/ssh/sshd_config sshd_config   ""
gather_file /etc/hosts           etc_hosts     ""
gather_file /etc/sudoers         sudoers       ""
gather_file /etc/os-release      os_release    ""

# ── 4. Log files ──────────────────────────────────────────────────────────────
gather_file /var/log/auth.log    auth_log      ""
gather_file /var/log/secure      secure        ""
gather_file /var/log/syslog      syslog        ""
gather_file /var/log/messages    messages      ""
gather_file /var/log/wtmp        wtmp          "" bin
gather_file /var/log/lastlog     lastlog       "" bin

# ── 5. Command outputs ────────────────────────────────────────────────────────
gather_cmd ip_addr       "" ip addr
gather_cmd ip_route      "" ip route
gather_cmd ip_neigh      "" ip neigh
gather_cmd arp           "" arp -a
gather_cmd netstat       "" netstat -tulpn
gather_cmd ss_output     "" ss -tulpn
gather_cmd iptables      "" iptables -S
gather_cmd nftables      "" nft list ruleset
gather_cmd ps_output     "" ps auxf
gather_cmd env_output    "" env
gather_cmd docker_ps     "" docker ps --all --no-trunc
gather_cmd docker_network "" docker network ls
gather_cmd kubectl_pods  "" kubectl get pods -A -o wide
gather_cmd last_output   "" last -F
gather_cmd uname_output  "" uname -a

# ── 6. Manifest emission ──────────────────────────────────────────────────────
# JSON shape:
#   { generated_at_utc, hostname, invoking_user,
#     files: [ {filename, file_type, username, source_path, stderr_present}, ... ] }
#
# Hand-rolled escaper: handles " and \. Paths containing newlines have those
# stripped (rare on Linux; safer than risking malformed JSON).
json_escape() {
    # stdin → stdout, escape \ and " and strip CR/LF.
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\r\n'
}

{
    printf '{\n'
    printf '  "generated_at_utc": "%s",\n' "$GENERATED_AT"
    printf '  "hostname": "%s",\n' "$(printf '%s' "$HOSTNAME_S" | json_escape)"
    printf '  "invoking_user": "%s",\n' "$(printf '%s' "$INVOKING_USER" | json_escape)"
    printf '  "files": [\n'
    entry_first=1
    # shellcheck disable=SC2162
    while IFS="$US" read -r ftype uname src archived stderr_p; do
        [ -n "$ftype" ] || continue
        if [ "$entry_first" -eq 1 ]; then
            entry_first=0
        else
            printf ',\n'
        fi
        printf '    {"filename": "%s", "file_type": "%s", "username": "%s", "source_path": "%s", "stderr_present": %s}' \
            "$(printf '%s' "$archived" | json_escape)" \
            "$(printf '%s' "$ftype" | json_escape)" \
            "$(printf '%s' "$uname" | json_escape)" \
            "$(printf '%s' "$src" | json_escape)" \
            "$stderr_p"
    done < "$ENTRIES_FILE"
    printf '\n  ]\n'
    printf '}\n'
} > "$STAGING/manifest.json"

# ── 7. Pack & summarize ───────────────────────────────────────────────────────
# Remove the entries side-file before packing (it's for the script, not import).
rm -f "$ENTRIES_FILE"

tar -C "$STAGING" -czf "$OUTFILE" . \
    || { printf 'lockpick_collect: tar failed\n' >&2; exit 1; }

n_files="$(find "$STAGING" -type f ! -name manifest.json | wc -l | tr -d ' ')"
n_errs="$(find "$STAGING" -type f -name '*.err' | wc -l | tr -d ' ')"

printf 'Wrote %s (%s files, %s with stderr).\n' "$OUTFILE" "$n_files" "$n_errs"
