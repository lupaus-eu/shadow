#!/usr/bin/env bash
# Disposable sshd test of the upload gate (TASK-059H2, ADR-013).
#
# Starts a throwaway Ubuntu 26.04 container with sshd, the schatten-upload
# account set up as documented for F, and root-installed upload-gate and
# schatten-receive from this working tree. Runs appleboy/scp-action's
# entrypoint at the commit pinned in deploy-production.yml, with that step's
# inputs, as the GitHub runner would. It first captures the remote commands
# (SSH_ORIGINAL_COMMAND) through a recording forced command, then uploads
# through upload-gate, accepts the upload with schatten-receive and the digest
# from the job summary, and checks that the key is refused for everything else.
#
# Usage: .github/scripts/verify-upload-gate.sh   (from inside the repository)
# Needs: docker, git, curl, python3, ssh, sftp, scp, ssh-keygen on an x86_64
# host with network access (APT, GitHub). Nothing outside the container and a
# temporary folder is changed; synthetic keys only.

set -Eeuo pipefail
export LC_ALL=C

repo="$(git rev-parse --show-toplevel)"
workflow="${repo}/.github/workflows/deploy-production.yml"
image="${QA_UBUNTU_IMAGE:-docker.io/library/ubuntu:26.04@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78}"
upload_root=/opt/apps/schatten-upload
work="$(mktemp -d "${TMPDIR:-/tmp}/upload-gate-qa.XXXXXX")"
container="schatten-upload-gate-qa-$$"
passes=0

cleanup() {
  docker rm --force "${container}" >/dev/null 2>&1 || true
  rm -rf "${work}"
}
trap cleanup EXIT

pass() {
  passes=$((passes + 1))
  printf 'PASS: %s\n' "$*"
}

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

in_ct() {
  docker exec -i "${container}" "$@"
}

# --- Pins and inputs from the workflow ------------------------------------
action_sha="$(sed -n 's#^ *uses: appleboy/scp-action@\([0-9a-f]\{40\}\) .*#\1#p' "${workflow}")"
drone_version="$(sed -n 's/^  DRONE_SCP_VERSION: "\([0-9.]*\)"$/\1/p' "${workflow}")"
drone_sha256="$(sed -n 's/^  DRONE_SCP_SHA256: \([0-9a-f]\{64\}\)$/\1/p' "${workflow}")"
[[ "${action_sha}" =~ ^[0-9a-f]{40}$ && -n "${drone_version}" && -n "${drone_sha256}" ]] \
  || fail "cannot read the pinned action and drone-scp from ${workflow}"
[[ "$(uname -m)" == x86_64 ]] || fail "run on x86_64 (the workflow pins the linux-amd64 binary)"

git init -q "${work}/scp-action"
git -C "${work}/scp-action" fetch -q --depth 1 https://github.com/appleboy/scp-action "${action_sha}"
git -C "${work}/scp-action" checkout -q FETCH_HEAD
[[ "$(git -C "${work}/scp-action" rev-parse HEAD)" == "${action_sha}" ]] || fail "action checkout is not ${action_sha}"
pass "appleboy/scp-action checked out at the pinned ${action_sha}"

# As the workflow does: verify drone-scp once and hand the action that file.
release_dir="${work}/drone-scp-release"
verified_binary="${release_dir}/v${drone_version}/drone-scp-${drone_version}-linux-amd64"
mkdir -p "${verified_binary%/*}"
curl -fsSL --retry 5 -o "${verified_binary}" \
  "https://github.com/appleboy/drone-scp/releases/download/v${drone_version}/drone-scp-${drone_version}-linux-amd64"
echo "${drone_sha256}  ${verified_binary}" | sha256sum --check --strict --quiet || fail "downloaded drone-scp hash differs"
chmod 0444 "${verified_binary}"
pass "drone-scp ${drone_version} verified before use"

# --- Source prepared exactly as the workflow does -------------------------
commit="$(git -C "${repo}" rev-parse HEAD)"
: >"${work}/github-output"
: >"${work}/summary.md"
(cd "${repo}" && GITHUB_SHA="${commit}" GITHUB_REF=refs/heads/main GITHUB_RUN_ID=2059 \
  GITHUB_OUTPUT="${work}/github-output" GITHUB_STEP_SUMMARY="${work}/summary.md" \
  .github/scripts/prepare-production-upload.sh "${work}/release-source" >/dev/null)
digest="$(sed -n 's/^| Manifest SHA-256 | `\([0-9a-f]\{64\}\)` |$/\1/p' "${work}/summary.md")"
[[ "${digest}" =~ ^[0-9a-f]{64}$ ]] || fail "no manifest SHA-256 in the job summary"
grep -qx "source_manifest_sha256=${digest}" "${work}/github-output" || fail "step output differs from summary"
if (cd "${repo}" && GITHUB_SHA="${commit}" GITHUB_REF=refs/heads/feature GITHUB_RUN_ID=1 \
  GITHUB_OUTPUT=/dev/null GITHUB_STEP_SUMMARY=/dev/null \
  .github/scripts/prepare-production-upload.sh "${work}/feature-source" >/dev/null 2>&1); then
  fail "prepare accepted refs/heads/feature"
fi
pass "prepare wrote commit ${commit:0:12} and manifest digest ${digest:0:12}... to the summary; a non-main ref is refused"

# --- Disposable sshd host --------------------------------------------------
ssh-keygen -q -t ed25519 -N '' -C qa-upload -f "${work}/upload_key"
docker run --detach --name "${container}" --publish 127.0.0.1::22 "${image}" sleep infinity >/dev/null
in_ct bash -c 'apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends openssh-server procps python3 >/dev/null'
docker cp "${repo}/deploy/bin/upload-gate" "${container}:/tmp/upload-gate"
docker cp "${repo}/deploy/bin/schatten-receive" "${container}:/tmp/schatten-receive"
docker cp "${work}/upload_key.pub" "${container}:/tmp/upload_key.pub"
in_ct bash -euo pipefail <<'EOF'
# Upload account and folders, as documented for F in docs/DEPLOYMENT.md.
useradd --user-group --create-home --shell /bin/bash deploy
passwd --lock deploy >/dev/null
useradd --user-group --no-create-home --home-dir /home/schatten-upload --shell /bin/sh schatten-upload
passwd --lock schatten-upload >/dev/null
usermod --append --groups schatten-upload deploy
install -d -o root -g root -m 0755 /home/schatten-upload /home/schatten-upload/.ssh
install -d -o root -g root -m 0755 /opt/apps
install -d -o schatten-upload -g schatten-upload -m 0750 /opt/apps/schatten-upload
install -d -o deploy -g deploy -m 0750 /opt/apps/schatten-sources
install -o root -g root -m 0755 /tmp/upload-gate /usr/local/bin/upload-gate
install -o root -g root -m 0755 /tmp/schatten-receive /usr/local/bin/schatten-receive
# Recording forced command, used only to capture the action's remote commands.
cat >/usr/local/bin/qa-record-command <<'REC'
#!/bin/bash
printf '%s\n' "${SSH_ORIGINAL_COMMAND-}" >>/opt/apps/schatten-upload/qa-captured-commands
exec /bin/sh -c "${SSH_ORIGINAL_COMMAND-}"
REC
chmod 0755 /usr/local/bin/qa-record-command
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nAllowUsers schatten-upload\n' \
  >/etc/ssh/sshd_config.d/10-qa.conf
ssh-keygen -A >/dev/null
install -d -m 0755 /run/sshd
/usr/sbin/sshd -t
/usr/sbin/sshd -E /var/log/sshd-qa.log
EOF
set_forced_command() {
  in_ct bash -c "printf 'restrict,command=\"%s\" %s\n' '$1' \"\$(cat /tmp/upload_key.pub)\" >/home/schatten-upload/.ssh/authorized_keys
    chown root:root /home/schatten-upload/.ssh/authorized_keys; chmod 0644 /home/schatten-upload/.ssh/authorized_keys"
}
set_forced_command /usr/local/bin/qa-record-command
port="$(docker port "${container}" 22/tcp | head -n 1)"
port="${port##*:}"
# drone-scp 1.8.0 (Go x/crypto 0.37.0) prefers ECDSA P-256 over RSA and
# Ed25519, so with Ubuntu's default host keys SSH_FINGERPRINT is the ECDSA key's.
fingerprint="$(in_ct ssh-keygen -l -E sha256 -f /etc/ssh/ssh_host_ecdsa_key.pub | cut -d ' ' -f 2)"
[[ "${fingerprint}" =~ ^SHA256:[A-Za-z0-9+/]{43}$ ]] || fail "unexpected host fingerprint ${fingerprint}"
in_ct bash -c 'for key in /etc/ssh/ssh_host_*_key.pub; do printf "[127.0.0.1]:%s %s\n" "$1" "$(cut -d " " -f 1,2 "$key")"; done' _ "${port}" \
  >"${work}/known_hosts"
printf 'Host: %s\n' "$(in_ct bash -c '. /etc/os-release; printf "%s, %s, %s" "${PRETTY_NAME}" "$(ssh -V 2>&1)" "$(tar --version | head -n 1)"')"
pass "sshd on 127.0.0.1:${port} (upload account locked, root-owned authorized_keys, public-key only)"

# --- The pinned action, with the workflow step's inputs -------------------
# Maps every INPUT_* of action.yml the way the runner does: the step's `with:`
# value (github.sha, env and secrets substituted), else the action default.
action_env() {
  QA_SSH_HOST=127.0.0.1 QA_SSH_USER=schatten-upload QA_SSH_KEY="$(cat "${work}/upload_key")" \
    QA_SSH_PORT="${port}" QA_SSH_FINGERPRINT="$1" \
    python3 - "${workflow}" "${work}/scp-action/action.yml" "${commit}" "${drone_version}" <<'PY'
import os, re, sys
workflow, action, sha, version = sys.argv[1:5]
lines = open(workflow).read().splitlines()
start = next(i for i, l in enumerate(lines) if re.match(r"\s+uses: appleboy/scp-action@", l))
indent = len(lines[start]) - len(lines[start].lstrip())
given = {}
i = start + 1
while i < len(lines) and lines[i].strip() != "with:":
    i += 1
for line in lines[i + 1:]:
    if len(line) - len(line.lstrip()) <= indent:
        break
    key, value = line.strip().split(":", 1)
    value = value.strip().replace("${{ github.sha }}", sha)
    value = value.replace("${{ env.DRONE_SCP_VERSION }}", version)
    value = re.sub(r"\$\{\{ secrets\.(\w+) \}\}", lambda m: os.environ["QA_" + m.group(1)], value)
    assert "${{" not in value, value
    given[key] = value
defaults, current = {}, None
section = None
mapping = []
for line in open(action).read().splitlines():
    if re.match(r"^\S", line):
        section = line.rstrip(":")
    elif section == "inputs" and re.match(r"^  \w+:$", line):
        current = line.strip().rstrip(":")
    elif section == "inputs" and re.match(r"^    default: ", line):
        defaults[current] = line.split(":", 1)[1].strip().strip('"')
    m = re.match(r"^\s+((?:INPUT_\w+)|DRONE_SCP_VERSION): \$\{\{ inputs\.(\w+) \}\}$", line)
    if m:
        mapping.append(m.groups())
unknown = set(given) - {name for _, name in mapping}
assert not unknown, f"with: inputs unknown to the action: {unknown}"
for env, name in mapping:
    sys.stdout.write(f"{env}={given.get(name, defaults.get(name, ''))}\0")
PY
}

run_action() {
  local -a inputs
  mapfile -d '' inputs < <(action_env "$1")
  (cd "${work}" && env -i PATH="${PATH}" HOME="${work}" GITHUB_ACTION_PATH="${work}/scp-action" \
    DRONE_SCP_RELEASE_URL="file://${release_dir}" "${inputs[@]}" bash "${work}/scp-action/entrypoint.sh")
}

reset_uploads() {
  in_ct bash -c "find ${upload_root} -mindepth 1 -delete"
}

# Phase 1: capture the remote commands through the recording forced command.
run_action "${fingerprint}" >"${work}/capture.log" 2>&1 || { cat "${work}/capture.log"; fail "capture upload failed"; }
captured="$(in_ct cat "${upload_root}/qa-captured-commands")"
printf 'Captured SSH_ORIGINAL_COMMAND sequence:\n%s\n' "${captured}"
alnum='[A-Za-z0-9]{10}'
expected="^ver
scp -tr ${upload_root}/(${alnum})\\.tar\\.gz
mkdir -p ${upload_root}/${commit}
tar -zxf ${upload_root}/(${alnum})\\.tar\\.gz --strip-components 1 --overwrite -C ${upload_root}/${commit}
rm -rf ${upload_root}/(${alnum})\\.tar\\.gz$"
[[ "${captured}" =~ ${expected} ]] || fail "captured commands differ from the forms upload-gate allows"
[[ "${BASH_REMATCH[1]}" == "${BASH_REMATCH[2]}" && "${BASH_REMATCH[1]}" == "${BASH_REMATCH[3]}" ]] \
  || fail "the captured commands name different archives"
pass "the action issues exactly ver, scp -tr, mkdir -p, tar -zxf ... --overwrite and rm -rf (the forms upload-gate allows)"
reset_uploads

# Phase 2: the same upload through upload-gate.
set_forced_command /usr/local/bin/upload-gate
run_action "${fingerprint}" >"${work}/upload.log" 2>&1 || { cat "${work}/upload.log"; fail "upload through upload-gate failed"; }
in_ct test -f "${upload_root}/${commit}/SOURCE_MANIFEST" || fail "SOURCE_MANIFEST was not delivered"
[[ -z "$(in_ct find "${upload_root}" -maxdepth 1 -name '*.tar.gz')" ]] || fail "the temporary archive was left behind"
[[ -z "$(in_ct find "${upload_root}/${commit}" -perm /0007)" ]] || fail "delivered files are accessible to others"
[[ -z "$(in_ct find "${upload_root}/${commit}" ! -user schatten-upload)" ]] || fail "delivered files not owned by schatten-upload"
pass "upload through upload-gate delivered ${upload_root}/${commit} (no access for others, archive removed)"
used_binary="${work}/scp-action/drone-scp-${drone_version}-linux-amd64"
grep -qF "from file://${release_dir}/v${drone_version}" "${work}/upload.log" \
  || { cat "${work}/upload.log"; fail "the action did not take the verified drone-scp"; }
echo "${drone_sha256}  ${used_binary}" | sha256sum --check --strict --quiet || fail "drone-scp hash differs"
pass "the action ran the pre-verified drone-scp ${drone_version} (file:// copy, recorded SHA-256), no new download"
run_action "${fingerprint}" >"${work}/overwrite.log" 2>&1 || { cat "${work}/overwrite.log"; fail "second upload (overwrite) failed"; }
pass "a repeated upload of the same commit overwrites through upload-gate"
if run_action "SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" >"${work}/wrong-fp.log" 2>&1; then
  fail "upload with a wrong host fingerprint succeeded"
fi
grep -q 'fingerprint mismatch' "${work}/wrong-fp.log" || { cat "${work}/wrong-fp.log"; fail "wrong fingerprint not reported"; }
pass "a wrong host-key fingerprint stops the action before any command"

# --- Receive with the digest from the job summary ------------------------
received="$(docker exec -u deploy "${container}" schatten-receive "${digest}")" || fail "schatten-receive refused the upload"
grep -qx "SOURCE_DIR=/opt/apps/schatten-sources/${commit}" <<<"${received}" || fail "unexpected receive output: ${received}"
docker exec -u deploy "${container}" schatten-receive --verify "/opt/apps/schatten-sources/${commit}" >/dev/null \
  || fail "accepted source does not verify"
pass "schatten-receive accepted the delivered upload with the summary digest; --verify passes"

# --- Everything else is refused -------------------------------------------
ssh_upload() {
  ssh -F /dev/null -i "${work}/upload_key" -p "${port}" -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${work}/known_hosts" -o ConnectTimeout=10 \
    schatten-upload@127.0.0.1 "$@"
}

expect_refused() {
  local label="$1" output
  shift
  if output="$(ssh_upload -T "$@" </dev/null 2>&1)"; then
    fail "${label}: accepted"
  fi
  grep -q 'upload-gate: refused' <<<"${output}" || fail "${label}: not refused by upload-gate: ${output}"
}

expect_failure() {
  local label="$1"
  shift
  if "$@" </dev/null >"${work}/case.log" 2>&1; then
    fail "${label}: succeeded"
  fi
}

other="${upload_root}/$(printf 'a%.0s' {1..40})"
tmp_archive="${upload_root}/QaQaQaQa01.tar.gz"
expect_refused "shell"
if ssh_upload -tt </dev/null >"${work}/case.log" 2>&1; then fail "pty shell: accepted"; fi
# restrict denies the pty; the gate then refuses the empty command.
grep -q 'PTY allocation request failed' "${work}/case.log" || fail "pty shell: pty not denied: $(cat "${work}/case.log")"
for command in "id" "sh -c id" "ver" "cat /etc/shadow" "bash" "internal-sftp" \
  "scp -t ${tmp_archive}" "scp -f ${upload_root}/${commit}/SOURCE_MANIFEST" "scp -tr /tmp/QaQaQaQa01.tar.gz" \
  "scp -tr ${upload_root}/${commit}/QaQaQaQa01.tar.gz" "scp -tr ${upload_root}/../QaQaQaQa01.tar.gz" \
  "mkdir -p /tmp/qa" "mkdir -p ${upload_root}/not-a-commit" "mkdir -p ${upload_root}/${commit}/sub" \
  "mkdir -p ${other}; id" "mkdir -p ${other} && id" "mkdir  -p ${other}" "mkdir -p ${other} \$(id)" \
  "tar -zxf ${tmp_archive} --strip-components 1 --overwrite -C /tmp" \
  "tar -zxf ${tmp_archive} --strip-components 0 --overwrite -C ${other}" \
  "tar -zxf /etc/passwd --strip-components 1 --overwrite -C ${other}" \
  "tar -xf ${tmp_archive} -C ${other}" \
  "rm -rf ${upload_root}/${commit}" "rm -rf ${upload_root}/${commit}/SOURCE_MANIFEST" "rm -rf ${upload_root}" \
  "rm -rf /tmp/QaQaQaQa01.tar.gz" "rm -f ${tmp_archive}" "rm -rf ${tmp_archive} ${upload_root}/${commit}"; do
  expect_refused "${command}" "${command}"
done
in_ct test -f "${upload_root}/${commit}/SOURCE_MANIFEST" || fail "an upload file was deleted"
pass "refused: shell (with and without pty), other commands, reads, other paths, injection, extra spaces and deletions"

expect_failure "sftp" sftp -F /dev/null -i "${work}/upload_key" -P "${port}" -o BatchMode=yes \
  -o UserKnownHostsFile="${work}/known_hosts" -b - schatten-upload@127.0.0.1
expect_failure "scp (SFTP protocol)" scp -F /dev/null -i "${work}/upload_key" -P "${port}" -o BatchMode=yes \
  -o UserKnownHostsFile="${work}/known_hosts" "${work}/upload_key.pub" "schatten-upload@127.0.0.1:${tmp_archive}"
expect_failure "scp -O (legacy protocol)" scp -O -F /dev/null -i "${work}/upload_key" -P "${port}" -o BatchMode=yes \
  -o UserKnownHostsFile="${work}/known_hosts" "${work}/upload_key.pub" "schatten-upload@127.0.0.1:${tmp_archive}"
expect_failure "stdio forwarding" ssh_upload -W 127.0.0.1:22
expect_failure "remote port forwarding" ssh_upload -N -o ExitOnForwardFailure=yes -R 127.0.0.1:2222:127.0.0.1:22
pass "refused: sftp, scp in both protocols, local (-W) and remote (-R) port forwarding"

# Serialization: while one gate command runs (an scp sink waiting for data),
# a parallel session must not be able to remove or upload an archive. The held
# session's stdin is a FIFO that stays open, as a client holding the gate busy
# would do; the gate's `timeout` must still end it and release the lock. The
# expiry is triggered with SIGALRM, which coreutils timeout handles exactly like
# its own timer running out. (On failure, cleanup removes the container.)
held_archive="${upload_root}/QaHeld0001.tar.gz"
held_scp="^scp -t -- ${held_archive}\$"
held_timeout="^timeout --kill-after=10s 10m scp -t -- ${held_archive}\$"
mkfifo "${work}/held.fifo"
ssh_upload -T "scp -tr ${held_archive}" <"${work}/held.fifo" >/dev/null 2>&1 &
held_pid=$!
exec 8>"${work}/held.fifo"
for _ in $(seq 50); do
  in_ct pgrep -u schatten-upload -f "${held_scp}" >/dev/null && break
  sleep 0.2
done
in_ct pgrep -u schatten-upload -f "${held_scp}" >/dev/null || fail "the held scp session did not start"
for command in "rm -rf ${tmp_archive}" "scp -tr ${tmp_archive}" "mkdir -p ${other}"; do
  if output="$(ssh_upload -T "${command}" </dev/null 2>&1)"; then
    fail "concurrent ${command}: accepted while another gate command ran"
  fi
  grep -q 'upload-gate: refused: another upload-gate command is running' <<<"${output}" \
    || fail "concurrent ${command}: not refused as busy: ${output}"
done
held_timer="$(in_ct pgrep -u schatten-upload -f "${held_timeout}")" \
  || fail "the held scp does not run under the gate's timeout 10m"
in_ct kill -ALRM "${held_timer}"
held_status=0
wait "${held_pid}" || held_status=$?
(( held_status == 124 )) || fail "the timed-out session ended with ${held_status}, not 124"
exec 8>&-
for _ in $(seq 50); do
  in_ct pgrep -u schatten-upload -f "${held_scp}" >/dev/null || break
  sleep 0.2
done
in_ct test ! -e "${held_archive}" || fail "the held session left ${held_archive}"
ssh_upload -T "mkdir -p ${other}" </dev/null || fail "the gate stayed locked after the held session timed out"
pass "a parallel rm, scp and mkdir are refused while another gate command runs; its timeout 10m ends a held session (exit 124) and releases the lock"

# Crafted archives through the allowed commands: nothing may land outside.
python3 - "${work}" <<'PY'
import io, sys, tarfile
work = sys.argv[1]
def archive(name, members):
    with tarfile.open(f"{work}/{name}", "w:gz") as tar:
        for info in members:
            data = b"qa\n" if info.type == tarfile.REGTYPE else None
            if data is not None:
                info.size = len(data)
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
def reg(name):
    return tarfile.TarInfo(name)
def link(name, target, kind):
    info = tarfile.TarInfo(name)
    info.type, info.linkname = kind, target
    return info
archive("escape.tar.gz", [reg("release-source/ok"),
    reg("release-source/../../../../tmp/qa-escape-dotdot"), reg("/tmp/qa-escape-abs")])
archive("symlink.tar.gz", [link("release-source/link", "/tmp", tarfile.SYMTYPE),
    reg("release-source/link/qa-escape-link")])
archive("hardlink.tar.gz", [link("release-source/hard", "/etc/hostname", tarfile.LNKTYPE)])
PY
upload_raw() {
  local file="$1" size
  size="$(stat -c %s "${file}")"
  { printf 'C0644 %s upload.tar.gz\n' "${size}"; cat "${file}"; printf '\0'; } \
    | ssh_upload -T "scp -tr ${tmp_archive}" >/dev/null 2>&1
}
extract() {
  ssh_upload -T "tar -zxf ${tmp_archive} --strip-components 1 --overwrite -C ${other}" </dev/null 2>&1
}
ssh_upload -T "mkdir -p ${other}" </dev/null
upload_raw "${work}/escape.tar.gz" || fail "raw scp upload through the gate failed"
if upload_raw "${work}/escape.tar.gz"; then fail "an existing archive name was overwritten"; fi
extract >"${work}/case.log" || true
in_ct test -f "${other}/ok" || fail "the regular member was not extracted"
for kind in symlink hardlink; do
  ssh_upload -T "rm -rf ${tmp_archive}" </dev/null
  upload_raw "${work}/${kind}.tar.gz" || fail "raw upload of the ${kind} archive failed"
  output="$(extract)" && fail "${kind} archive extracted"
  grep -q 'upload-gate: refused' <<<"${output}" || fail "${kind} archive not refused by upload-gate"
done
ssh_upload -T "rm -rf ${tmp_archive}" </dev/null
in_ct ln -s /tmp "${other}/planted-link"
upload_raw "${work}/escape.tar.gz" || fail "raw upload failed"
output="$(extract)" && fail "extraction into a folder with a symlink succeeded"
grep -q 'upload-gate: refused' <<<"${output}" || fail "planted symlink not refused by upload-gate"
ssh_upload -T "rm -rf ${tmp_archive}" </dev/null
outside="$(in_ct find / -xdev \( -path /proc -o -path "${upload_root}" \) -prune -o -user schatten-upload -print)"
[[ -z "${outside}" ]] || fail "files owned by schatten-upload outside the upload area: ${outside}"
in_ct test ! -e /tmp/qa-escape-dotdot -a ! -e /tmp/qa-escape-abs -a ! -e /tmp/qa-escape-link \
  || fail "a crafted member escaped the upload folder"
pass "crafted archives: .. and absolute members stay inside, symlink/hardlink members and a symlinked folder are refused, no file outside the upload area"

in_ct grep -q 'Accepted publickey for schatten-upload' /var/log/sshd-qa.log || fail "sshd log has no accepted upload key"
printf 'Upload gate QA: %s checks passed\n' "${passes}"
