#!/usr/bin/env bash
# Disposable end-to-end QA for the UpCloud production runtime (TASK-059G), the
# integrated first-installation runbook sequence (TASK-059E), the Git-free
# source path (TASK-059H1): source manifest -> upload-style folder ->
# shadow-receive -> build-release --source, and the server Makefile and
# service command (TASK-059H3): build, first-install, deploy, backup, restore,
# status, ps, logs, stop and start run through deploy/Makefile from the
# verified source copy.
#
# Runs every deploy/bin command against an isolated Docker-in-Docker daemon
# with synthetic configuration, a throwaway GPG key and simulated OIDC
# settings. Never touches the developer's or production Docker resources:
# all containers, volumes and images live inside the disposable daemon and
# all host paths live under a temporary directory. Git is used only for the
# runner-side manifest; every server-side step runs with a PATH without Git.
#
# Usage: .github/scripts/verify-production-runtime.sh
#   QA_SOURCE_REPO / QA_COMMIT select the committed source to build (default HEAD).
#   QA_DIND_IMAGE selects another digest-pinned daemon, for example the Engine
#   major version expected on the target host.

set -Eeuo pipefail

repo="$(git rev-parse --show-toplevel)"
source_repo="${QA_SOURCE_REPO:-${repo}}"
commit="${QA_COMMIT:-$(git -C "${source_repo}" rev-parse HEAD)}"
dind_image="${QA_DIND_IMAGE:-docker.io/library/docker:28.5.2-dind@sha256:2a232a42256f70d78e3cc5d2b5d6b3276710a0de0596c145f627ecfae90282ac}"
cli_image="docker.io/library/docker:28.5.2-cli@sha256:625d9431a9f54c5a2bc90f24f0e1c3d55b1349fd857dd85035f98c2c9acbdd4d"
postgres_image="docker.io/library/postgres:18.6@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280"
ofelia_image="docker.io/mcuadros/ofelia:0.3.22@sha256:efcbe2c5cf658a25de6443c1462d653f9cc03791d642e01fc6c638a00f97e492"
host_socket_gid="$(stat -c %g /var/run/docker.sock)"

qa_root="$(mktemp -d "${RUNNER_TEMP:-/tmp}/shadow-runtime-qa.XXXXXX")"
# Unix socket paths are limited to 108 bytes, so the socket gets a short directory.
socket_dir="$(mktemp -d /tmp/sqa.XXXXXX)"
dind="shadow-runtime-qa-$$"
# Set QA_LOG_FILE to keep the detailed, secret-free log as evidence.
log_file="${QA_LOG_FILE:-${qa_root}/qa.log}"
bin="${repo}/deploy/bin"

cleanup() {
  local status=$?
  # The disposable daemon and its files are removed through the host daemon
  # (DOCKER_HOST points at the disposable daemon during the run).
  env -u DOCKER_HOST docker rm --force --volumes "${dind}" >/dev/null 2>&1 || true
  env -u DOCKER_HOST docker run --rm --volume "${qa_root}:${qa_root}" --entrypoint rm "${cli_image}" -rf "${qa_root}" >/dev/null 2>&1 || true
  rm -rf "${qa_root}" "${socket_dir}" 2>/dev/null || true
  exit "${status}"
}
trap cleanup EXIT

step() { printf '\n==> %s\n' "$*" | tee -a "${log_file}"; }
pass() { printf 'PASS %s\n' "$*" | tee -a "${log_file}"; }
fail() { printf 'FAIL %s\n' "$*" | tee -a "${log_file}" >&2; exit 1; }
expect_failure() {
  local description="$1" pattern="$2"
  shift 2
  local output
  if output="$("$@" 2>&1)"; then
    printf '%s\n' "${output}" | tee -a "${log_file}" | tail -n 20 >&2
    fail "${description}: command unexpectedly succeeded"
  fi
  printf '%s\n' "${output}" >>"${log_file}"
  if ! grep -Eq "${pattern}" <<<"${output}"; then
    printf '%s\n' "${output}" | tail -n 20 >&2
    fail "${description}: missing /${pattern}/"
  fi
  pass "${description}"
}
run() { "$@" 2>&1 | tee -a "${log_file}"; return "${PIPESTATUS[0]}"; }
# Run a command that prints KEY=value; echo the value or fail with its output.
capture() {
  local key="$1" output value
  shift
  if ! output="$("$@" 2>&1)"; then
    printf '%s\n' "${output}" | tee -a "${log_file}" | tail -n 25 >&2
    fail "$* failed"
  fi
  printf '%s\n' "${output}" >>"${log_file}"
  value="$(sed -n "s/^${key}=//p" <<<"${output}" | tail -n 1)"
  [[ -n "${value}" ]] || fail "$* reported no ${key}"
  printf '%s' "${value}"
}

step "Start isolated Docker daemon"
# Only Unix sockets: no Docker TCP listener, even inside the disposable daemon.
# A container-level /tmp stops the dind wrapper from hiding /tmp bind mounts.
docker run --detach --privileged --name "${dind}" \
  --tmpfs /tmp:exec,mode=1777 \
  --volume "${qa_root}:${qa_root}" --volume "${socket_dir}:${socket_dir}" \
  --entrypoint sh "${dind_image}" -c \
  "rm -f /var/run/docker.pid /var/run/docker/containerd/containerd.pid; exec dind dockerd --host=unix:///var/run/docker.sock --host=unix://${socket_dir}/docker.sock --group=${host_socket_gid}" \
  >/dev/null
export DOCKER_HOST="unix://${socket_dir}/docker.sock"
for attempt in $(seq 1 60); do
  docker version >/dev/null 2>&1 && break
  [[ "${attempt}" == 60 ]] && fail "isolated daemon did not start"
  sleep 1
done
# Per-network address: newer Engines no longer return the deprecated top-level
# NetworkSettings.IPAddress. Resolved here, not inside later arguments, so a
# failed lookup stops the run instead of becoming an empty address.
resolve_dind_ip() {
  dind_ip="$(env -u DOCKER_HOST docker inspect --format '{{(index .NetworkSettings.Networks "bridge").IPAddress}}' "${dind}")" \
    || fail "could not inspect the isolated daemon's bridge address"
  [[ "${dind_ip}" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || fail "isolated daemon has no IPv4 bridge address: '${dind_ip}'"
}
resolve_dind_ip
for image in "${cli_image}" "${postgres_image}" "${ofelia_image}"; do
  docker pull --quiet "${image}" >/dev/null
done
pass "isolated daemon ${dind} with socket group ${host_socket_gid}"

step "Prepare synthetic host layout, key pair and configuration"
opt="${qa_root}/opt"
config_dir="${opt}/apps/shadow-config"
mkdir -p "${config_dir}" "${opt}/apps/shadow-state" "${opt}/apps/shadow-releases" "${qa_root}/keys" "${opt}/caddy"
as_root() { docker run --rm --volume "${qa_root}:${qa_root}" --entrypoint sh "${cli_image}" -c "$1"; }
as_root "mkdir -p '${opt}/postgres-backups' && chown 10002:10002 '${opt}/postgres-backups' && chmod 0700 '${opt}/postgres-backups'"
# The runbook recommends a passphrase-protected private key held offline.
key_passphrase="qa-key-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
(umask 077 && printf '%s\n' "${key_passphrase}" >"${qa_root}/keys/backup-key-passphrase")
docker run --rm --user "$(id -u):$(id -g)" --env HOME=/tmp --volume "${qa_root}:${qa_root}" \
  --entrypoint bash "${postgres_image}" -c "
    export GNUPGHOME=\$(mktemp -d)
    gpg --batch --quiet --pinentry-mode loopback --passphrase-file '${qa_root}/keys/backup-key-passphrase' \
      --quick-generate-key 'Shadow QA backup <qa@example.test>' default default never
    gpg --batch --armor --export > '${config_dir}/backup-public-key.asc'
    gpg --batch --pinentry-mode loopback --passphrase-file '${qa_root}/keys/backup-key-passphrase' \
      --armor --export-secret-keys > '${qa_root}/keys/backup-private-key.asc'"
chmod 0600 "${qa_root}/keys/backup-private-key.asc"
db_password="qa-db-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
client_secret="qa-oidc-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
env_file="${config_dir}/production.env"
cat >"${env_file}" <<EOF
POSTGRES_DB=shadow
POSTGRES_USER=shadow
POSTGRES_PASSWORD=${db_password}
DATABASE_URL=postgresql://shadow:${db_password}@database:5432/shadow
OIDC_DISCOVERY_URL=https://login.microsoftonline.com/qa-tenant/v2.0/.well-known/openid-configuration
OIDC_ISSUER=https://login.microsoftonline.com/qa-tenant/v2.0
OIDC_CLIENT_ID=qa-client
OIDC_CLIENT_SECRET=${client_secret}
PUBLIC_ORIGIN=https://app.example.test
DOCKER_SOCKET_GID=${host_socket_gid}
SHADOW_BACKUP_PUBLIC_KEY=${config_dir}/backup-public-key.asc
SHADOW_BACKUP_DIR=${opt}/postgres-backups
SHADOW_STATE_DIR=${opt}/apps/shadow-state
SHADOW_RELEASES_DIR=${opt}/apps/shadow-releases
SHADOW_SOURCES_DIR=${opt}/apps/shadow-sources
SHADOW_BACKUP_LOCK_TIMEOUT_SECONDS=3
EOF
chmod 0600 "${env_file}"
upload_root="${opt}/apps/shadow-upload"
export SHADOW_ENV_FILE="${env_file}" SHADOW_SOURCES_DIR="${opt}/apps/shadow-sources" SHADOW_UPLOAD_DIR="${upload_root}"
# QA-only override: internal TLS issuer and a simulated Entra discovery endpoint
# on a separate network, trusted through a throwaway CA. Production is unchanged.
override="${qa_root}/qa-override.yml"
cat >"${override}" <<OVERRIDE
services:
  frontend:
    environment:
      CADDY_TLS_MODE: internal
  backend:
    environment:
      SSL_CERT_FILE: /run/qa/oidc-ca.pem
    volumes:
      - ${qa_root}/oidc/ca.pem:/run/qa/oidc-ca.pem:ro
    networks:
      qa-oidc: {}
networks:
  qa-oidc:
    external: true
    name: shadow-qa-oidc
OVERRIDE
export SHADOW_COMPOSE_OVERRIDE_FILE="${override}"
mkdir -p "${qa_root}/oidc"
cp "${repo}/.github/scripts/mock-oidc-discovery.py" "${qa_root}/oidc/"
docker run --rm --user "$(id -u):$(id -g)" --volume "${qa_root}:${qa_root}" --workdir "${qa_root}/oidc" \
  --entrypoint bash "${postgres_image}" -c "
    openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.pem -days 2 -subj '/CN=Shadow QA OIDC CA' 2>/dev/null
    openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj '/CN=login.microsoftonline.com' 2>/dev/null
    printf 'subjectAltName=DNS:login.microsoftonline.com\nbasicConstraints=CA:FALSE\n' > server.ext
    openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out server.pem -days 2 -extfile server.ext 2>/dev/null
    chmod 0644 server.key"
# shellcheck source=../../deploy/lib/common.sh
source "${repo}/deploy/lib/common.sh"
set +e
load_config
set -e
locks="${opt}/apps/shadow-state/locks"
pass "synthetic configuration, throwaway key pair and QA-only internal TLS override"

step "Source manifest of ${commit} (runner side; the only Git use)"
manifest_tool="${repo}/.github/scripts/create-source-manifest.sh"
in_dir() { (cd "$1" && shift && "$@"); }
qa_run_id=1059
upload="${upload_root}/${commit}"
manifest_args=(--commit "${commit}" --ref refs/heads/main --run-id "${qa_run_id}")
digest="$(capture SOURCE_MANIFEST_SHA256 in_dir "${source_repo}" "${manifest_tool}" "${manifest_args[@]}" --output "${upload}")"
repeat="$(capture SOURCE_MANIFEST_SHA256 in_dir "${source_repo}" "${manifest_tool}" "${manifest_args[@]}" --output "${qa_root}/manifest-repeat")"
[[ "${repeat}" == "${digest}" ]] && cmp -s "${upload}/SOURCE_MANIFEST" "${qa_root}/manifest-repeat/SOURCE_MANIFEST" \
  || fail "manifest is not byte-identical for the same commit and inputs"
[[ "$(sha256sum <"${upload}/SOURCE_MANIFEST" | cut -d ' ' -f 1)" == "${digest}" ]] || fail "printed manifest digest"
tree="$(git -C "${source_repo}" ls-tree -r --full-tree "${commit}")"
listed="$(sed -n '7,$p' "${upload}/SOURCE_MANIFEST")"
[[ "$(wc -l <<<"${listed}")" == "$(wc -l <<<"${tree}")" ]] \
  && grep -qx "SOURCE_FILE_COUNT=$(wc -l <<<"${tree}")" "${upload}/SOURCE_MANIFEST" || fail "manifest does not list every tracked file"
[[ "$(grep -c '^755 ' <<<"${listed}")" == "$(grep -c '^100755 ' <<<"${tree}")" ]] || fail "manifest executable modes"
compose_hash="$(git -C "${source_repo}" show "${commit}:docker-compose.production.yml" | sha256sum | cut -d ' ' -f 1)"
grep -qx "644 ${compose_hash} docker-compose.production.yml" <<<"${listed}" || fail "manifest hash of docker-compose.production.yml"
grep -Eqx '755 [0-9a-f]{64} deploy/bin/build-release' <<<"${listed}" || fail "manifest mode of deploy/bin/build-release"
source_date_epoch="$(git -C "${source_repo}" show -s --format=%ct "${commit}")"
grep -qx "SOURCE_DATE_EPOCH=${source_date_epoch}" "${upload}/SOURCE_MANIFEST" || fail "manifest SOURCE_DATE_EPOCH"
qa_git() {
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    git -C "$1" -c user.name=QA -c user.email=qa@example.test -c commit.gpgsign=false "${@:2}"
}
for kind in symlink submodule; do
  scratch="${qa_root}/manifest-${kind}"
  mkdir -p "${scratch}"
  qa_git "${scratch}" init --quiet
  printf 'fixture\n' >"${scratch}/file"
  qa_git "${scratch}" add file
  qa_git "${scratch}" commit --quiet -m base
  if [[ "${kind}" == symlink ]]; then
    ln -s file "${scratch}/link"
    qa_git "${scratch}" add link
  else
    qa_git "${scratch}" update-index --add --cacheinfo "160000,$(qa_git "${scratch}" rev-parse HEAD),vendored"
  fi
  qa_git "${scratch}" commit --quiet -m "${kind}"
  expect_failure "manifest refuses a ${kind}" "${kind} [a-z]+ is not allowed" in_dir "${scratch}" "${manifest_tool}" \
    --commit "$(qa_git "${scratch}" rev-parse HEAD)" --ref refs/heads/main --run-id 1 --output "${scratch}-export"
done
# Like repeated SCP uploads: a stale file from an earlier upload and modes
# that differ from the manifest.
printf 'stale\n' >"${upload}/stale-from-an-earlier-upload.txt"
mkdir -p "${upload}/stale-dir"
printf 'stale\n' >"${upload}/stale-dir/old.txt"
chmod 0755 "${upload}/docker-compose.production.yml"
chmod 0644 "${upload}/deploy/bin/build-release"
pass "deterministic manifest ${digest} lists all $(wc -l <<<"${tree}") tracked files with Git modes and hashes; symlink and submodule refused"

step "Server-side steps run with a PATH without Git"
nogit_bin="${qa_root}/nogit-bin"
mkdir -p "${nogit_bin}"
# The real interpreter, not a version-manager shim that would search PATH.
ln -s "$(python3 -c 'import os, sys; print(os.path.realpath(sys.executable))')" "${nogit_bin}/python3"
IFS=: read -r -a path_dirs <<<"${PATH}"
for directory in "${path_dirs[@]}"; do
  [[ -d "${directory}" ]] || continue
  for tool in "${directory}"/*; do
    name="${tool##*/}"
    [[ -x "${tool}" && ! -d "${tool}" && "${name}" != git && "${name}" != git-* ]] || continue
    [[ -e "${nogit_bin}/${name}" || -L "${nogit_bin}/${name}" ]] || ln -s "${tool}" "${nogit_bin}/${name}"
  done
done
export PATH="${nogit_bin}"
hash -r
if command -v git >/dev/null 2>&1; then fail "git is still reachable on the server-side PATH"; fi
pass "git is not on PATH for the remaining steps"

step "Host prerequisite check and explicit state initialization"
expect_failure "check-host reports missing lock files before init-state" 'missing .*maintenance.lock' \
  "${bin}/check-host" --allow-os-mismatch
run "${bin}/init-state"
output="$("${bin}/check-host" --allow-os-mismatch 2>&1)" || { printf '%s\n' "${output}"; fail "check-host"; }
printf '%s\n' "${output}" >>"${log_file}"
chmod 0644 "${env_file}"
expect_failure "protected env file must be private" 'must not be group/other accessible' "${bin}/check-host" --allow-os-mismatch
chmod 0600 "${env_file}"
pass "check-host accepts the prepared baseline"

step "Verified receive: rejections, acceptance, stale files and manifest modes"
sources="${opt}/apps/shadow-sources"
rejects="${qa_root}/rejects"
reject_copy() {
  mkdir -p "${rejects}/$1"
  cp -a "${upload}" "${rejects}/$1/${commit}"
  printf '%s' "${rejects}/$1/${commit}"
}
# A crafted manifest with its own digest, so the check under test is reached.
craft() {
  mkdir -p "${rejects}/$1/${commit}"
  sed "$2" "${upload}/SOURCE_MANIFEST" >"${rejects}/$1/${commit}/SOURCE_MANIFEST"
  printf '%s %s' "$(sha256sum <"${rejects}/$1/${commit}/SOURCE_MANIFEST" | cut -d ' ' -f 1)" "${rejects}/$1/${commit}"
}
receive() { "${bin}/shadow-receive" "$@"; }
expect_failure "receive rejects a wrong digest" 'does not equal the operator-supplied digest' \
  receive "$(printf '0%.0s' {1..64})" --upload "${upload}"
expect_failure "receive finds no upload for an unknown digest" 'no upload under' receive "$(printf 'a%.0s' {1..64})"
dir="$(reject_copy changed)"
printf 'tampered\n' >>"${dir}/docker-compose.production.yml"
expect_failure "receive rejects a changed file" 'docker-compose.production.yml does not match its manifest' receive "${digest}" --upload "${dir}"
dir="$(reject_copy missing)"
rm "${dir}/frontend/Caddyfile"
expect_failure "receive rejects a missing file" 'frontend/Caddyfile is missing' receive "${digest}" --upload "${dir}"
dir="$(reject_copy symlinked-file)"
mv "${dir}/frontend/Caddyfile" "${rejects}/Caddyfile.elsewhere"
ln -s "${rejects}/Caddyfile.elsewhere" "${dir}/frontend/Caddyfile"
expect_failure "receive rejects a symlinked file" 'frontend/Caddyfile is a symlink' receive "${digest}" --upload "${dir}"
dir="$(reject_copy symlinked-parent)"
mv "${dir}/frontend" "${rejects}/frontend.elsewhere"
ln -s "${rejects}/frontend.elsewhere" "${dir}/frontend"
expect_failure "receive rejects a symlinked parent" 'parent frontend of frontend/.* is a symlink' receive "${digest}" --upload "${dir}"
mkdir -p "${rejects}/symlinked-upload"
ln -s "${upload}" "${rejects}/symlinked-upload/${commit}"
expect_failure "receive rejects a symlinked upload folder" "${commit} is a symlink" receive "${digest}" --upload "${rejects}/symlinked-upload/${commit}"
dir="$(reject_copy fifo)"
rm "${dir}/frontend/Caddyfile"
mkfifo "${dir}/frontend/Caddyfile"
expect_failure "receive rejects a non-regular file" 'frontend/Caddyfile is not a regular file' receive "${digest}" --upload "${dir}"
read -r crafted dir <<<"$(craft dotdot '7s# [^ ]*$# ../outside#')"
expect_failure "receive rejects a '..' path" "'\.\.' component" receive "${crafted}" --upload "${dir}"
read -r crafted dir <<<"$(craft absolute '7s# [^ ]*$# /etc/passwd#')"
expect_failure "receive rejects an absolute path" 'is absolute' receive "${crafted}" --upload "${dir}"
read -r crafted dir <<<"$(craft duplicate '7p')"
expect_failure "receive rejects a duplicate entry" 'duplicate entry' receive "${crafted}" --upload "${dir}"
read -r crafted dir <<<"$(craft ref 's#^SOURCE_REF=.*#SOURCE_REF=refs/heads/feature#')"
expect_failure "receive rejects a non-main ref" 'is not refs/heads/main' receive "${crafted}" --upload "${dir}"
other="${rejects}/other-commit/$(printf 'f%.0s' {1..40})"
mkdir -p "${other}"
cp "${upload}/SOURCE_MANIFEST" "${other}/"
expect_failure "receive rejects a commit that is not the upload folder name" 'does not match the upload folder name' receive "${digest}" --upload "${other}"
[[ -z "$(ls -A "${sources}")" ]] || fail "a rejected receive left files in ${sources}"
source_dir="$(capture SOURCE_DIR receive "${digest}")"
[[ "${source_dir}" == "${sources}/${commit}" ]] || fail "receive SOURCE_DIR ${source_dir}"
[[ ! -e "${source_dir}/stale-from-an-earlier-upload.txt" && ! -e "${source_dir}/stale-dir" ]] || fail "stale upload files were accepted"
[[ "$(stat -c %a "${source_dir}/docker-compose.production.yml") $(stat -c %a "${source_dir}/deploy/bin/build-release")" == "444 555" ]] \
  || fail "accepted modes do not come from the manifest"
[[ -z "$(find "${source_dir}" -perm /222 -print -quit)" ]] || fail "accepted source is not read-only"
printf 'changed after acceptance\n' >>"${upload}/docker-compose.production.yml"
run receive --verify "${source_dir}" >/dev/null || fail "accepted source does not verify against its manifest"
[[ "$(sha256sum <"${source_dir}/docker-compose.production.yml" | cut -d ' ' -f 1)" == "${compose_hash}" ]] \
  || fail "an upload change after acceptance reached the accepted source"
expect_failure "receive never replaces an accepted source" 'already exists' receive "${digest}" --upload "${upload}"
expect_failure "build-release no longer takes a commit" 'Usage: build-release --source' "${bin}/build-release" "${commit}"
# A self-consistent read-only folder verifies against its own manifest, so only
# the location check stops a folder that never passed the operator digest.
mkdir -p "${rejects}/outside"
cp -a "${source_dir}" "${rejects}/outside/${commit}"
run "${bin}/shadow-receive" --verify "${rejects}/outside/${commit}" >/dev/null || fail "outside copy should verify on its own"
expect_failure "build-release refuses a folder outside the sources directory" 'is not an accepted source under' \
  "${bin}/build-release" --source "${rejects}/outside/${commit}"
unverified="${sources}/$(printf 'e%.0s' {1..40})"
cp -a "${rejects}/changed/${commit}" "${unverified}"
expect_failure "build-release refuses a folder that fails verification" 'failed manifest verification' \
  "${bin}/build-release" --source "${unverified}"
rm -rf "${unverified}"
[[ -z "$(find "${opt}/apps/shadow-releases" -maxdepth 1 -name '*.incomplete' -print -quit)" ]] || fail "failed build left a work directory"
pass "all rejection cases leave nothing behind; the accepted read-only copy ignores stale files, takes manifest modes and is unaffected by later upload changes; build-release accepts only verified folders under the sources directory"

step "Server Makefile: thin wrappers without destructive operations"
# As on the host, make runs from the verified read-only copy (runbook 3).
make_dir="${source_dir}/deploy"
op() { make -C "${make_dir}" "$@"; }
makefile="${make_dir}/Makefile"
targets="$(sed -n 's/^\.PHONY: //p' "${makefile}" | tr ' ' '\n' | sort | paste -sd' ' -)"
[[ "${targets}" == "audit backup build check cleanup-dry-run deploy first-install help logs ps restore start status stop" ]] \
  || fail "Makefile targets: ${targets}"
wrapped="$(grep -o "'\$(BIN)/[a-z-]*'" "${makefile}" | tr -d "'" | sed 's#.*/##' | sort -u)"
for command in ${wrapped}; do
  [[ -x "${make_dir}/bin/${command}" ]] || fail "Makefile wraps a missing command ${command}"
done
[[ "$(wc -w <<<"${wrapped}")" == 9 ]] || fail "Makefile wraps: ${wrapped}"
if grep -F '$(BIN)/' "${makefile}" | grep -Eq -- '(down|prune|volume|rm |--apply|--rollback|initialize|seed|bootstrap|shadow-receive)'; then
  fail "a Makefile recipe runs a destructive or initialization command"
fi
for target in deploy first-install; do
  expect_failure "make ${target} requires RELEASE" 'RELEASE is required' op "${target}"
  expect_failure "make ${target} requires APPROVAL" 'APPROVAL is required' op "${target}" RELEASE=20260101T000000Z-000000000000
  expect_failure "make ${target} refuses a release of another commit" 'was not built from this source copy' \
    op "${target}" RELEASE=20260101T000000Z-000000000000 APPROVAL=qa
done
expect_failure "make restore requires BACKUP" 'BACKUP is required' op restore KEY=/dev/null
expect_failure "make restore requires KEY" 'KEY is required' op restore BACKUP=shadow-x
expect_failure "make restore refuses a relative KEY" 'KEY must be an absolute path' op restore BACKUP=shadow-x KEY=key.asc
expect_failure "make restore refuses a relative PASSPHRASE" 'PASSPHRASE must be an absolute path' \
  op restore BACKUP=shadow-x KEY=/dev/null PASSPHRASE=passphrase
expect_failure "make logs refuses an unknown service" 'Unknown service' op logs SERVICE=bogus
expect_failure "make logs refuses shell syntax in SERVICE" 'Unknown service' op logs 'SERVICE=backend; touch /tmp/pwned'
expect_failure "make ps needs a current release" 'No current release' op ps
# check-host itself is tested above with --allow-os-mismatch; through make it
# must pass on Ubuntu 26.04 and otherwise stop only at the OS check.
if output="$(op check 2>&1)"; then
  grep -q 'PASSED host prerequisites' <<<"${output}" || fail "make check"
else
  [[ "$(grep -c '^error' <<<"${output}")" == 1 ]] && grep -q '^error  OS .* is not the approved ubuntu 26.04' <<<"${output}" \
    || { printf '%s\n' "${output}" >&2; fail "make check reported more than the OS mismatch"; }
fi
printf '%s\n' "${output}" >>"${log_file}"
pass "Makefile has exactly the documented targets over ${wrapped//$'\n'/, }; variables are required and not evaluated by a shell; restore paths must be absolute; no destructive recipe"

step "Build frozen release artifacts from the verified source"
release_one="$(capture RELEASE_ID op build)"
dir_one="$(release_dir "${release_one}")"
for pair in "SOURCE_COMMIT=${commit}" "SOURCE_MANIFEST_SHA256=${digest}" SOURCE_REF=refs/heads/main \
  "SOURCE_RUN_ID=${qa_run_id}" "SOURCE_DATE_EPOCH=${source_date_epoch}"; do
  grep -qx "${pair}" "${dir_one}/release.env" || fail "release.env lacks ${pair}"
done
grep -q '^GIT_VERSION=' "${dir_one}/release.env" && fail "release.env still records GIT_VERSION"
run "${bin}/shadow-receive" --verify "${dir_one}/source" >/dev/null || fail "frozen release source does not match its manifest"
for kind in BACKEND FRONTEND; do
  tag="$(release_value "${dir_one}" "${kind}_IMAGE")"
  [[ "$(docker image inspect --format '{{.Id}}' "${tag}")" == "$(release_value "${dir_one}" "${kind}_IMAGE_ID")" ]] || fail "${kind} image ID"
done
[[ ! -w "${dir_one}/source/docker-compose.production.yml" ]] || fail "release source is not frozen read-only"
# As documented for operators, later commands run from the frozen release.
bin="${dir_one}/source/deploy/bin"
pass "release ${release_one} records commit, manifest digest, ref, run ID, tools and matching immutable image IDs"

step "Simulated Entra discovery endpoint"
docker network create shadow-qa-oidc >/dev/null
docker run --detach --name qa-oidc --network shadow-qa-oidc --network-alias login.microsoftonline.com \
  --restart unless-stopped --user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --sysctl net.ipv4.ip_unprivileged_port_start=443 \
  --volume "${qa_root}/oidc:/qa:ro" --env QA_TLS_CERT=/qa/server.pem --env QA_TLS_KEY=/qa/server.key \
  --entrypoint python "$(release_value "${dir_one}" BACKEND_IMAGE_ID)" /qa/mock-oidc-discovery.py >/dev/null
pass "simulated login.microsoftonline.com discovery on an isolated QA network"

step "First-install deployment (no previous release)"
expect_failure "deployment requires an approval reference" 'approval' "${bin}/deploy-release" "${release_one}" --first-install
run op first-install RELEASE="${release_one}" APPROVAL=qa-first-install
[[ "$(cat "${opt}/apps/shadow-releases/current")" == "${release_one}" ]] || fail "current pointer"
[[ ! -e "${opt}/apps/shadow-releases/previous" ]] || fail "first release must have no previous target"
expect_failure "second first-install is refused on an initialized database" 'already has migration history' \
  "${bin}/deploy-release" "${release_one}" --approval qa --first-install
pass "migration-gated first install with pre-migration baseline backup"

step "Published ports, TLS, redirect, headers and proxy trust"
published="$(docker ps --format '{{.Label "com.docker.compose.service"}} {{.Ports}}' | awk 'NF > 1 && $0 ~ /->/')"
[[ "$(wc -l <<<"${published}")" == 1 && "${published}" == frontend* ]] || fail "only frontend publishes ports: ${published}"
grep -q '0.0.0.0:80->80/tcp' <<<"${published}" && grep -q '0.0.0.0:443->443/tcp' <<<"${published}" || fail "80/443 bindings"
https() { curl --silent --show-error --insecure --resolve "app.example.test:443:${dind_ip}" "$@"; }
[[ "$(https https://app.example.test/health)" == OK ]] || fail "HTTPS health"
headers="$(https --dump-header - --output /dev/null https://app.example.test/)"
for header in 'strict-transport-security: max-age=31536000' 'x-frame-options: DENY' "content-security-policy: default-src 'self'"; do
  grep -qi "^${header}" <<<"${headers}" || fail "missing header ${header}"
done
redirect="$(curl --silent --output /dev/null --write-out '%{http_code} %{redirect_url}' --resolve "app.example.test:80:${dind_ip}" http://app.example.test/login)"
[[ "${redirect}" == "308 https://app.example.test/login" ]] || fail "HTTP redirect: ${redirect}"
https https://app.example.test/workspace/deep-link | grep -q '<div id="root"></div>' || fail "SPA fallback"
issuer="$(echo | openssl s_client -connect "${dind_ip}:443" -servername app.example.test 2>/dev/null | openssl x509 -noout -issuer)"
grep -q 'Caddy Local Authority' <<<"${issuer}" || fail "internal QA certificate issuer: ${issuer}"
status="$(https --output /dev/null --write-out '%{http_code}' \
  --header 'X-Shadow-Client-IP: 203.0.113.40' --header 'X-Forwarded-For: 203.0.113.30' \
  --header 'Forwarded: for=203.0.113.30' https://app.example.test/api/v1/auth/session)"
[[ "${status}" == 401 ]] || fail "API through Caddy with spoofed headers returned ${status} (expected 401, 400 means untrusted peer)"
direct="$(docker run --rm --network shadow_edge "${cli_image}" sh -c \
  "wget -S -O /dev/null --header 'Host: app.example.test' --header 'X-Shadow-Client-IP: 203.0.113.40' http://backend:8000/api/v1/auth/session 2>&1 | grep -Eo 'HTTP/1\.[01] [0-9]{3}' | head -n 1 | cut -d' ' -f2")"
[[ "${direct}" == 400 ]] || fail "backend trusted a non-Caddy peer (status ${direct})"
pass "only Caddy 80/443 published; TLS, HSTS/CSP, redirect, SPA, sanitized forwarding and exact Caddy-peer trust"

step "Service commands through make: ps, logs, stop and start keep containers and volumes"
project_containers() { docker ps --all --quiet --no-trunc --filter label=com.docker.compose.project=shadow | sort; }
running_services() { compose_release "${dir_one}" ps --status running --services | sort | paste -sd' ' -; }
ps_output="$(op ps 2>&1)" || { printf '%s\n' "${ps_output}" >&2; fail "make ps"; }
printf '%s\n' "${ps_output}" >>"${log_file}"
grep -q "^release ${release_one}\$" <<<"${ps_output}" || fail "make ps does not name the current release"
for service in database migration backend prediction-worker frontend; do
  grep -Eq "^${service} +shadow-${service}-1 " <<<"${ps_output}" || fail "make ps lacks ${service}"
done
logs_output="$(op logs 2>&1)" || fail "make logs"
backend_logs="$(op logs SERVICE=backend 2>&1)" || fail "make logs SERVICE=backend"
printf '%s\n%s\n' "${logs_output}" "${backend_logs}" >>"${log_file}"
grep -q '^database-1 ' <<<"${logs_output}" && grep -q '^backend-1 ' <<<"${logs_output}" || fail "make logs lacks service output"
grep -Ev '^backend-1 ' <<<"${backend_logs}" | grep -q -- '-1 ' && fail "make logs SERVICE=backend printed other services"
grep -Eq '(POSTGRES_PASSWORD|DATABASE_URL|OIDC_CLIENT_SECRET)=' <<<"${ps_output}${logs_output}" && fail "service output contains environment"
containers_before="$(project_containers)"
volumes_before="$(docker volume ls --quiet | sort)"
migration_started="$(docker inspect --format '{{.State.StartedAt}}' "$(compose_release "${dir_one}" ps --all --quiet migration)")"
[[ "$(running_services)" == "backend database frontend prediction-worker" ]] || fail "unexpected running services: $(running_services)"
run op stop
[[ -z "$(running_services)" ]] || fail "make stop left $(running_services) running"
[[ "$(project_containers)" == "${containers_before}" && "$(docker volume ls --quiet | sort)" == "${volumes_before}" ]] \
  || fail "make stop removed or created containers or volumes"
grep -qx 'SERVICES=database backend prediction-worker frontend' "${opt}/apps/shadow-state/stopped-services" || fail "stop record"
expect_failure "a second stop before start is refused" 'still stopped by an earlier service stop' op stop
deployments_before="$(find "${opt}/apps/shadow-state/deployments" -type f | wc -l)"
expect_failure "deploy is refused while services are stopped" 'stopped by service stop' \
  op deploy RELEASE="${release_one}" APPROVAL=qa-stopped
expect_failure "rollback is refused while services are stopped" 'stopped by service stop' \
  "${bin}/deploy-release" "${release_one}" --approval qa-stopped --rollback --confirm-schema-compatible
[[ -z "$(running_services)" && "$(cat "${opt}/apps/shadow-releases/current")" == "${release_one}" ]] \
  || fail "a refused deploy started services or moved the current pointer"
[[ "$(find "${opt}/apps/shadow-state/deployments" -type f | wc -l)" == "${deployments_before}" ]] \
  || fail "a refused deploy wrote a deployment record"
status_output="$(op status 2>&1)" || { printf '%s\n' "${status_output}" >&2; fail "make status while stopped"; }
printf '%s\n' "${status_output}" >>"${log_file}"
grep -q '^stopped by service stop' <<<"${status_output}" \
  && grep -qx '  SERVICES=database backend prediction-worker frontend' <<<"${status_output}" \
  || fail "make status does not show the stopped services"
run op start
grep -q '^stopped by service stop' <<<"$(op status 2>&1)" && fail "make status still shows stopped services after start"
[[ "$(running_services)" == "backend database frontend prediction-worker" ]] || fail "make start did not restore the services"
for service in database backend prediction-worker frontend; do
  wait_for_healthy "${dir_one}" "${service}" 5 || fail "${service} unhealthy after make start"
done
[[ "$(project_containers)" == "${containers_before}" && "$(docker volume ls --quiet | sort)" == "${volumes_before}" ]] \
  || fail "make start replaced containers or volumes"
[[ "$(docker inspect --format '{{.State.StartedAt}}' "$(compose_release "${dir_one}" ps --all --quiet migration)")" == "${migration_started}" ]] \
  || fail "make start re-ran the migration job"
[[ ! -e "${opt}/apps/shadow-state/stopped-services" ]] || fail "stop record left after start"
expect_failure "start without a recorded stop is refused" 'No services were recorded' op start
[[ "$(https https://app.example.test/health)" == OK ]] || fail "HTTPS after make start"
pass "make ps/logs show the current release without environment; stop/start keep the same containers and volumes and never rerun the migration; deploy and rollback are refused and make status lists the stopped services while stopped"

step "Explicit first initialization: migrations -> reference seed -> administrator bootstrap"
# Count-only status; never prints names, emails or rows.
init_status() {
  local output
  output="$("${bin}/initialize" status 2>&1)" || { printf '%s\n' "${output}" >&2; fail "initialize status"; }
  printf '%s\n' "${output}" >>"${log_file}"
  printf '%s' "${output}"
}
expect_status() {
  local output="$1" description="$2" pair
  shift 2
  for pair in "$@"; do
    grep -qx "${pair}" <<<"${output}" || { printf '%s\n' "${output}" >&2; fail "${description}: expected ${pair}"; }
  done
}
migrations_expected="$(find "${dir_one}/source/db/migrations" -maxdepth 1 -name '[0-9][0-9][0-9]_*.sql' ! -name '*.down.sql' | wc -l)"
initial="$(init_status)"
expect_status "${initial}" "no implicit startup seed or bootstrap" "schema_version=${migrations_expected}" active_default_metamodels=0 \
  users_including_deleted=0 user_identities=0 auth_sessions=0 organisations=0
run "${bin}/initialize" reference-seed
seeded="$(init_status)"
expect_status "${seeded}" "reference seed" active_default_metamodels=1 users_including_deleted=0 organisations=0
grep -Eqx 'node_types=[1-9][0-9]*' <<<"${seeded}" && grep -Eqx 'allowed_connections=[1-9][0-9]*' <<<"${seeded}" \
  || fail "reference seed did not create metamodel types and connection rules"
run "${bin}/initialize" reference-seed
[[ "$(init_status)" == "${seeded}" ]] || fail "repeated reference seed changed data"
expect_failure "bootstrap-admin refuses a non-interactive session" 'interactive terminal' "${bin}/initialize" bootstrap-admin </dev/null
# Drive the interactive prompts through a pseudo-terminal with synthetic input.
# The container terminal echoes typed input once; the command must not print it.
bootstrap_interactive() {
  QA_ADMIN_NAME="QA Bootstrap Admin" QA_ADMIN_EMAIL="qa-bootstrap-admin@example.test" \
    python3 - "${bin}/initialize" bootstrap-admin <<'PY'
import os, pty, re, select, sys, time

name, email = os.environ["QA_ADMIN_NAME"], os.environ["QA_ADMIN_EMAIL"]
pid, fd = pty.fork()
if pid == 0:
    os.execv(sys.argv[1], sys.argv[1:])
answers = [(rb"display name: ", name), (rb"Entra email: ", email)]
output, position, deadline = b"", 0, time.time() + 300
while time.time() < deadline:
    if select.select([fd], [], [], 1)[0]:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
        if answers:
            match = re.search(answers[0][0], output[position:])
            if match:
                position += match.end()
                os.write(fd, answers.pop(0)[1].encode() + b"\n")
else:
    os.kill(pid, 9)
_, status = os.waitpid(pid, 0)
text = output.decode(errors="replace")
print(f"email_occurrences={text.count(email)} name_occurrences={text.count(name)}")
print(text.replace(email, "[synthetic-email]").replace(name, "[synthetic-name]"))
sys.exit(os.waitstatus_to_exitcode(status))
PY
}
output="$(bootstrap_interactive 2>&1)" || { printf '%s\n' "${output}" | tail -n 20 >&2; fail "interactive bootstrap-admin"; }
printf '%s\n' "${output}" >>"${log_file}"
grep -q 'Administrator bootstrap completed.' <<<"${output}" || fail "bootstrap did not report completion"
grep -qx 'email_occurrences=1 name_occurrences=1' <<<"${output}" || fail "bootstrap printed its private input beyond the terminal echo"
bootstrapped="$(init_status)"
expect_status "${bootstrapped}" "administrator bootstrap" users_including_deleted=1 active_admins=1 \
  user_identities=0 auth_sessions=0 organisations=0 active_default_metamodels=1
output="$(bootstrap_interactive 2>&1)" && { printf '%s\n' "${output}" >&2; fail "repeated bootstrap unexpectedly succeeded"; }
printf '%s\n' "${output}" >>"${log_file}"
grep -q 'refused: the users table is not empty' <<<"${output}" || fail "repeated bootstrap was not refused"
[[ "$(init_status)" == "${bootstrapped}" ]] || fail "refused bootstrap changed data"
pass "status shows no startup seed; explicit idempotent seed; interactive empty-table bootstrap creates one admin, no identity/session/dev data; repeat refused unchanged"

step "On-demand encrypted backup and isolated restore rehearsal"
backup_id="$(capture BACKUP_ID op backup)"
facts="$(as_root "cd '${opt}/postgres-backups' && stat -c '%a %u' ${backup_id}.dump.gpg ${backup_id}.manifest && head -c 5 ${backup_id}.dump.gpg | od -An -c")"
[[ "$(sed -n 1p <<<"${facts}")" == "600 10002" && "$(sed -n 2p <<<"${facts}")" == "600 10002" ]] || fail "backup file ownership/mode: ${facts}"
grep -q 'P   G   D   M   P' <<<"${facts}" && fail "backup file is an unencrypted pg_dump archive"
printf 'wrong-passphrase\n' >"${qa_root}/keys/wrong-passphrase"
expect_failure "restore with the wrong key passphrase fails" 'Restore rehearsal failed' \
  "${bin}/restore-rehearsal" "${backup_id}" --private-key "${qa_root}/keys/backup-private-key.asc" \
  --passphrase-file "${qa_root}/keys/wrong-passphrase"
expect_failure "failed latest restore evidence blocks release" 'not successful' \
  "${bin}/deploy-release" "${release_one}" --approval qa-failed-restore-evidence
evidence="$(capture RESTORE_EVIDENCE op restore BACKUP="${backup_id}" KEY="${qa_root}/keys/backup-private-key.asc" \
  PASSPHRASE="${qa_root}/keys/backup-key-passphrase")"
grep -qx 'STATUS=success' "${evidence}" || fail "restore evidence"
grep -q 'check=schema-migrations result=pass' "${evidence}" || fail "restore schema check"
grep -q 'rows table=schema_migrations count=' "${evidence}" || fail "restore data check"
# The initialized database, not an empty schema, is what restores.
for pair in users=1 metamodels=1 user_identities=0 auth_sessions=0 organisations=0; do
  grep -q "rows table=${pair%=*} count=${pair#*=}\$" "${evidence}" || fail "restored initialized data: expected ${pair}"
done
grep -Eq 'rows table=node_types count=[1-9]' "${evidence}" || fail "restored reference data"
[[ -z "$(docker ps --all --quiet --filter label=eu.lupaus.shadow.disposable=restore)" ]] || fail "restore target not removed"
status_output="$(op status 2>&1)" || fail "make status"
printf '%s\n' "${status_output}" >>"${log_file}"
grep -qx "${backup_id}" <<<"${status_output}" && grep -q 'STATUS=success' <<<"${status_output}" || fail "ops-status summary"
pass "initialized-database backup ${backup_id} is encrypted 0600; failed evidence blocks release; passphrase-key restore verifies admin/reference rows in a removed disposable target"

step "Backup failure reporting and retention"
variant() {
  local file="${qa_root}/variant.env"
  sed "/^$1=/d" "${env_file}" >"${file}"
  [[ -n "${2:-}" ]] && printf '%s=%s\n' "$1" "$2" >>"${file}"
  chmod 0600 "${file}"
  printf '%s' "${file}"
}
count_manifests() { as_root "ls '$1' | grep -c '\\.manifest\$' || true"; }
before="$(count_manifests "${opt}/postgres-backups")"
expect_failure "missing public key fails" 'no such file|not exist|missing' \
  env SHADOW_ENV_FILE="$(variant SHADOW_BACKUP_PUBLIC_KEY "${config_dir}/absent.asc")" "${bin}/backup-now"
cp "${qa_root}/keys/backup-private-key.asc" "${config_dir}/secret-key.asc"
chmod 0644 "${config_dir}/secret-key.asc"
expect_failure "secret key material is refused in the runner" 'refusing secret key material' \
  env SHADOW_ENV_FILE="$(variant SHADOW_BACKUP_PUBLIC_KEY "${config_dir}/secret-key.asc")" "${bin}/backup-now"
rm -f "${config_dir}/secret-key.asc"
expect_failure "missing database credential fails" 'DATABASE_URL' \
  env SHADOW_ENV_FILE="$(variant DATABASE_URL)" "${bin}/backup-now"
expect_failure "wrong database credential fails" 'database connection failed' \
  env SHADOW_ENV_FILE="$(variant DATABASE_URL "postgresql://shadow:wrong@database:5432/shadow")" "${bin}/backup-now"
as_root "mkdir -p '${opt}/backups-denied' && chmod 0755 '${opt}/backups-denied'"
expect_failure "permission denied fails" 'not writable' \
  env SHADOW_ENV_FILE="$(variant SHADOW_BACKUP_DIR "${opt}/backups-denied")" "${bin}/backup-now"
mkdir -p "${opt}/backups-full"
env -u DOCKER_HOST docker exec "${dind}" mount -t tmpfs -o size=4k,uid=10002,gid=10002,mode=0700 tmpfs "${opt}/backups-full"
expect_failure "disk full fails without publishing" 'file write failed' \
  env SHADOW_ENV_FILE="$(variant SHADOW_BACKUP_DIR "${opt}/backups-full")" "${bin}/backup-now"
[[ "$(as_root "find '${opt}/backups-full' -type f | wc -l")" == 0 ]] || fail "disk-full run left files"
# exec keeps the lock on the killable process itself (no child keeps it).
(exec 9<"${locks}/backup.lock"; flock --exclusive 9; exec sleep 15) &
lock_holder=$!
sleep 1
expect_failure "overlapping backup is refused" 'another backup is still running' "${bin}/backup-now"
kill "${lock_holder}" 2>/dev/null || true
wait "${lock_holder}" 2>/dev/null || true
[[ "$(count_manifests "${opt}/postgres-backups")" == "${before}" ]] || fail "a failed run published a backup"
stamp() { date -u -d "$1" +%Y%m%dT%H%M%SZ; }
old="shadow-$(stamp '10 days ago')-scheduled-aaaaaa"
recent="shadow-$(stamp '6 days ago')-scheduled-bbbbbb"
orphan="shadow-$(stamp '3 days ago')-scheduled-cccccc"
as_root "cd '${opt}/postgres-backups' && for f in ${old}.dump.gpg ${old}.manifest ${recent}.dump.gpg ${recent}.manifest ${orphan}.dump.gpg notes.txt other-tool-backup.sql.gz shadow-foreign.manifest; do echo fixture > \$f; touch -t $(date -u -d '30 days ago' +%Y%m%d%H%M) \$f; chown 10002:10002 \$f; done"
retention_id="$(capture BACKUP_ID "${bin}/backup-now")"
listing="$(as_root "ls -1 '${opt}/postgres-backups'")"
for gone in "${old}.dump.gpg" "${old}.manifest" "${orphan}.dump.gpg"; do
  grep -qx "${gone}" <<<"${listing}" && fail "retention kept ${gone}"
done
for kept in "${recent}.manifest" "${recent}.dump.gpg" notes.txt other-tool-backup.sql.gz shadow-foreign.manifest "${retention_id}.manifest" "${backup_id}.manifest"; do
  grep -qx "${kept}" <<<"${listing}" || fail "retention removed ${kept}"
done
pass "key/credential/permission/disk-full/overlap failures publish nothing; 7-day retention prunes only job-owned files"

step "Persistence across container replacement"
fingerprint() { echo | openssl s_client -connect "${dind_ip}:443" -servername app.example.test 2>/dev/null | openssl x509 -noout -fingerprint -sha256; }
cert_before="$(fingerprint)" || fail "could not read the certificate fingerprint before container replacement"
[[ -n "${cert_before}" ]] || fail "no certificate fingerprint before container replacement"
migrations_before="$(compose_release "${dir_one}" exec -T database sh -c 'psql -X -A -t -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM schema_migrations"')"
compose_release "${dir_one}" up --detach --no-build --pull never --no-deps --force-recreate database frontend >>"${log_file}" 2>&1
wait_for_healthy "${dir_one}" database && wait_for_healthy "${dir_one}" frontend || fail "replaced containers unhealthy"
[[ "$(fingerprint)" == "${cert_before}" ]] || fail "certificate storage did not persist"
[[ "$(compose_release "${dir_one}" exec -T database sh -c 'psql -X -A -t -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM schema_migrations"')" == "${migrations_before}" ]] || fail "database did not persist"
pass "certificate and database volumes survive container replacement"

step "Host reboot simulation (daemon restart)"
migration_started="$(docker inspect --format '{{.State.StartedAt}}' "$(compose_release "${dir_one}" ps --all --quiet migration)")"
# Clean shutdown like a host reboot: the daemon stops its containers first.
env -u DOCKER_HOST docker restart --time 120 "${dind}" >/dev/null
for attempt in $(seq 1 60); do
  docker version >/dev/null 2>&1 && break
  [[ "${attempt}" == 60 ]] && fail "isolated daemon did not come back after restart"
  sleep 1
done
# The bridge address can change when the daemon container restarts.
resolve_dind_ip
for service in database backend prediction-worker frontend; do
  wait_for_healthy "${dir_one}" "${service}" 90 || fail "${service} did not recover after restart"
done
[[ "$(docker inspect --format '{{.State.StartedAt}}' "$(compose_release "${dir_one}" ps --all --quiet migration)")" == "${migration_started}" ]] || fail "migration re-ran on reboot"
[[ "$(docker inspect --format '{{.State.Running}}' shadow-backup-runner shadow-docker-cleanup | sort -u)" == false ]] || fail "runners started on reboot"
[[ "$(https https://app.example.test/health)" == OK ]] || fail "HTTPS after restart"
pass "long-running services restart without re-running migration or runners"

step "Ofelia scheduling, hardening and label isolation"
cat >"${qa_root}/qa-ofelia.ini" <<'EOF'
[job-run "postgres-backup"]
schedule = @every 20s
container = shadow-backup-runner
no-overlap = true

[job-run "docker-cleanup"]
schedule = @every 20s
container = shadow-docker-cleanup
no-overlap = true
EOF
printf 'SHADOW_OFELIA_CONFIG=%s\n' "${qa_root}/qa-ofelia.ini" >>"${env_file}"
docker run --detach --name qa-label-decoy --label ofelia.enabled=true \
  --label 'ofelia.job-exec.decoy.schedule=@every 5s' --label 'ofelia.job-exec.decoy.command=touch /tmp/decoy' \
  "${cli_image}" sleep 600 >/dev/null
run "${bin}/deploy-release" "${release_one}" --approval qa-scheduler --enable-scheduler
sleep 50
ofelia_logs="$(docker logs "$(compose_release "${dir_one}" --profile scheduler ps --quiet ofelia)" 2>&1)"
printf '%s\n' "${ofelia_logs}" >>"${log_file}"
grep -q 'Job "postgres-backup".*failed: false' <<<"${ofelia_logs}" || fail "scheduled backup did not succeed"
grep -q 'Job "docker-cleanup".*Finished' <<<"${ofelia_logs}" || fail "scheduled cleanup did not run"
grep -q decoy <<<"${ofelia_logs}" && fail "label job was discovered"
as_root "ls '${opt}/postgres-backups'" | grep -q -- '-scheduled-[0-9a-f]\{6\}\.manifest$' || fail "no scheduled backup manifest"
output="$("${bin}/verify-runtime-hardening" 2>&1)" || { printf '%s\n' "${output}"; fail "runtime hardening"; }
printf '%s\n' "${output}" >>"${log_file}"
# stop/start with the scheduler: stop refuses while a scheduled backup runs.
for attempt in $(seq 1 10); do
  output="$(op stop 2>&1)" && break
  grep -q 'A backup is running' <<<"${output}" || { printf '%s\n' "${output}" >&2; fail "make stop with the scheduler"; }
  [[ "${attempt}" == 10 ]] && fail "make stop found a backup running 10 times"
  sleep 3
done
printf '%s\n' "${output}" >>"${log_file}"
grep -qx 'SERVICES=database backend prediction-worker frontend ofelia' "${opt}/apps/shadow-state/stopped-services" || fail "stop record with ofelia"
[[ -z "$(compose_release "${dir_one}" --profile scheduler ps --status running --quiet)" ]] || fail "make stop left the scheduler running"
run op start
[[ -n "$(compose_release "${dir_one}" --profile scheduler ps --status running --quiet ofelia)" ]] || fail "make start did not restart the scheduler"
docker run --rm --volume "${dir_one}/source/deploy/ofelia/config.ini:/etc/ofelia/config.ini:ro" "${ofelia_image}" \
  validate --config=/etc/ofelia/config.ini >>"${log_file}" 2>&1 || fail "production Ofelia job file is invalid"
docker run --detach --name qa-ofelia-nosocket --user 65534:65534 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --network none \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume "${qa_root}/qa-ofelia.ini:/etc/ofelia/config.ini:ro" \
  "${ofelia_image}" daemon --config /etc/ofelia/config.ini >/dev/null
sleep 25
nosocket_logs="$(docker logs qa-ofelia-nosocket 2>&1 || true)"
docker rm --force qa-ofelia-nosocket >/dev/null 2>&1 || true
printf '%s\n' "${nosocket_logs}" >>"${log_file}"
grep -qi 'permission denied' <<<"${nosocket_logs}" || fail "missing socket group did not fail visibly"
[[ "$(stat -c %a "${socket_dir}/docker.sock")" == 660 ]] || fail "socket permissions changed"
compose_release "${dir_one}" --profile scheduler stop ofelia >>"${log_file}" 2>&1
docker rm --force qa-label-decoy >/dev/null
pass "hardened Ofelia runs fixed jobs only, ignores labels and fails visibly without socket group"

step "Release-aware Docker cleanup with fixture resources"
docker run --name qa-exited "${cli_image}" true >/dev/null
docker run --name qa-exited-retained --label eu.lupaus.shadow.retain=true "${cli_image}" true >/dev/null
docker run --detach --name qa-running "${cli_image}" sleep 600 >/dev/null
docker volume create qa-fixture-volume >/dev/null
fixture_image() { printf 'FROM %s\nLABEL qa.fixture=%s\n' "${cli_image}" "$1" | docker build --quiet --tag "$2" - ; }
unprotected_id="$(fixture_image unprotected shadow-backend:qa-unprotected)"
protected_id="$(fixture_image previous shadow-backend:qa-previous-release)"
fixture_image dangling shadow-frontend:qa-dangling >/dev/null
fixture_image dangling-replaced shadow-frontend:qa-dangling >/dev/null
fake_previous="${opt}/apps/shadow-releases/20000101T000000Z-000000000000"
mkdir -p "${fake_previous}"
printf 'BACKEND_IMAGE_ID=%s\nFRONTEND_IMAGE_ID=%s\n' "${protected_id}" "${protected_id}" >"${fake_previous}/release.env"
volumes_before="$(docker volume ls --quiet | sort)"
backups_before="$(as_root "ls -1 '${opt}/postgres-backups' | sort")"
future=$(( $(date -u +%s) + 8 * 86400 ))
cleanup_run() { compose_release "${dir_one}" --profile ops run --rm --no-deps -T --env "SHADOW_CLEANUP_NOW_EPOCH=${future}" "$@"; }
run op cleanup-dry-run >/dev/null || fail "make cleanup-dry-run"
dry="$(cleanup_run cleanup-runner --dry-run 2>&1)"
printf '%s\n' "${dry}" >>"${log_file}"
grep -q 'candidate container=/qa-exited ' <<<"${dry}" && grep -q "candidate image=${unprotected_id}" <<<"${dry}" || fail "dry-run candidates"
docker inspect qa-exited "${unprotected_id}" >/dev/null || fail "dry-run removed resources"
(exec 9<"${locks}/maintenance.lock"; flock --shared 9; exec sleep 10) &
lock_holder=$!
sleep 1
set +e
held="$(cleanup_run cleanup-runner --apply 2>&1)"
held_status=$?
set -e
kill "${lock_holder}" 2>/dev/null || true
wait "${lock_holder}" 2>/dev/null || true
[[ "${held_status}" == 75 ]] && grep -q 'status=skipped' <<<"${held}" || fail "cleanup did not skip while an operation held the lock"
expect_failure "cleanup without socket access reports failure" 'status=failed' \
  cleanup_run --user 65534:65534 cleanup-runner --apply
# A reachable API whose listing or prune calls fail must not look like success.
mkdir -p "${qa_root}/docker-shim"
cat >"${qa_root}/docker-shim/docker" <<'EOF'
#!/bin/sh
case "$1" in
  version) exit 0 ;;
  "${QA_FAIL}") exit 1 ;;
  ps|images) exit 0 ;;
  *) exit 1 ;;
esac
EOF
chmod 0755 "${qa_root}/docker-shim/docker"
for failing in ps images builder; do
  expect_failure "cleanup reports a failed docker ${failing} call" 'status=failed' \
    docker run --rm --network none --read-only --tmpfs /tmp:size=1m --user 65534:65534 \
      --volume "${dir_one}/source/deploy/ops:/opt/shadow-ops:ro" --volume "${locks}:/locks:ro" \
      --volume "${qa_root}/docker-shim:/qa-shim:ro" --env QA_FAIL="${failing}" \
      --env PATH=/qa-shim:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
      --entrypoint /opt/shadow-ops/docker-cleanup.sh "${cli_image}" --apply
done
applied="$(cleanup_run cleanup-runner --apply 2>&1)"
printf '%s\n' "${applied}" >>"${log_file}"
grep -q 'status=completed mode=--apply' <<<"${applied}" || fail "cleanup apply"
docker inspect qa-exited >/dev/null 2>&1 && fail "old exited container kept"
docker image inspect "${unprotected_id}" >/dev/null 2>&1 && fail "unprotected release image kept"
[[ -z "$(docker images --quiet --filter dangling=true --filter label=qa.fixture=dangling)" ]] || fail "dangling fixture kept"
docker inspect qa-exited-retained qa-running shadow-backup-runner shadow-docker-cleanup >/dev/null || fail "retained/running container removed"
docker image inspect "${protected_id}" "$(release_value "${dir_one}" BACKEND_IMAGE_ID)" "$(release_value "${dir_one}" FRONTEND_IMAGE_ID)" >/dev/null || fail "protected image removed"
[[ "$(docker volume ls --quiet | sort)" == "${volumes_before}" ]] || fail "cleanup changed volumes"
[[ "$(as_root "ls -1 '${opt}/postgres-backups' | sort")" == "${backups_before}" ]] || fail "cleanup changed backup files"
docker rm --force qa-running qa-exited-retained >/dev/null
docker volume rm qa-fixture-volume >/dev/null
rm -rf "${fake_previous}"
pass "cleanup dry-run, lock skip, failure reporting and protected volumes/backups/current/previous images"

step "Standard release, restore-evidence gate, migration failure gate and rollback"
sleep 1
release_two="$(capture RELEASE_ID "${bin}/build-release" --source "${source_dir}")"
[[ "${release_two}" != "${release_one}" ]] || fail "second build-release reused the release ID"
dir_two="$(release_dir "${release_two}")"
mv "${opt}/apps/shadow-state/restore-evidence" "${opt}/apps/shadow-state/restore-evidence.hidden"
mkdir -m 0700 "${opt}/apps/shadow-state/restore-evidence"
expect_failure "missing restore evidence blocks release" 'Missing restore-rehearsal evidence' \
  "${bin}/deploy-release" "${release_two}" --approval qa-release-two
rmdir "${opt}/apps/shadow-state/restore-evidence"
mv "${opt}/apps/shadow-state/restore-evidence.hidden" "${opt}/apps/shadow-state/restore-evidence"
run op deploy RELEASE="${release_two}" APPROVAL=qa-release-two
[[ "$(cat "${opt}/apps/shadow-releases/current")" == "${release_two}" && "$(cat "${opt}/apps/shadow-releases/previous")" == "${release_one}" ]] || fail "release pointers"
expect_failure "current release cannot be retired" 'Refusing to retire' "${bin}/retire-release" "${release_two}"

psql_db() { compose_release "${dir_two}" exec -T database sh -c "psql -X -A -t -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"$1\""; }
original_checksum="$(psql_db 'SELECT checksum FROM schema_migrations WHERE version = 1')"
backend_before="$(docker inspect --format '{{.Id}} {{.State.StartedAt}}' "$(compose_release "${dir_two}" ps --quiet backend)")"
worker_before="$(docker inspect --format '{{.Id}} {{.State.StartedAt}}' "$(compose_release "${dir_two}" ps --quiet prediction-worker)")"
psql_db "UPDATE schema_migrations SET checksum = repeat('0', 64) WHERE version = 1" >/dev/null
expect_failure "failed migration blocks the release" 'Migration failed' \
  "${bin}/deploy-release" "${release_two}" --approval qa-migration-failure
[[ "$(docker inspect --format '{{.Id}} {{.State.StartedAt}}' "$(compose_release "${dir_two}" ps --quiet backend)")" == "${backend_before}" ]] || fail "backend replaced after failed migration"
[[ "$(docker inspect --format '{{.Id}} {{.State.StartedAt}}' "$(compose_release "${dir_two}" ps --quiet prediction-worker)")" == "${worker_before}" ]] || fail "worker replaced after failed migration"
grep -l 'STATUS=failed' "${opt}/apps/shadow-state/deployments/"*"${release_two}.env" >/dev/null || fail "failed deployment record"
grep -l 'SERVICES_REPLACED=false' "${opt}/apps/shadow-state/deployments/"*"${release_two}.env" >/dev/null || fail "failed migration record claims replaced services"
expect_failure "rollback requires schema confirmation" 'confirm-schema-compatible' \
  "${bin}/deploy-release" "${release_one}" --approval qa-rollback --rollback
expect_failure "rollback refuses divergent migration history" 'incompatible with the applied migration history' \
  "${bin}/deploy-release" "${release_one}" --approval qa-rollback --rollback --confirm-schema-compatible
psql_db "UPDATE schema_migrations SET checksum = '${original_checksum}' WHERE version = 1" >/dev/null
migration_started="$(docker inspect --format '{{.State.StartedAt}}' "$(compose_release "${dir_two}" ps --all --quiet migration)")"
run "${bin}/deploy-release" "${release_one}" --approval qa-rollback --rollback --confirm-schema-compatible
[[ "$(cat "${opt}/apps/shadow-releases/current")" == "${release_one}" && "$(cat "${opt}/apps/shadow-releases/previous")" == "${release_two}" ]] || fail "rollback pointers"
[[ "$(docker inspect --format '{{.State.StartedAt}}' "$(compose_release "${dir_one}" ps --all --quiet migration)")" == "${migration_started}" ]] || fail "rollback ran migrations"
[[ "$(psql_db "SELECT count(*) FROM schema_migrations")" == "${migrations_before}" ]] || fail "rollback changed schema history"
# A gate failing after migration leaves new-release containers running; the
# failure must say so, and the same release must be able to fix forward.
unhealthy_override="${qa_root}/qa-override-unhealthy.yml"
awk '{ print } /^  frontend:$/ { print "    healthcheck:"; print "      test: [\"CMD\", \"false\"]"; print "      interval: 1s"; print "      retries: 1"; print "      start_period: 0s" }' \
  "${override}" >"${unhealthy_override}"
expect_failure "post-migration gate failure reports partly running release" 'may be partly running' \
  env SHADOW_COMPOSE_OVERRIDE_FILE="${unhealthy_override}" "${bin}/deploy-release" "${release_two}" --approval qa-post-migration-failure
[[ "$(cat "${opt}/apps/shadow-releases/current")" == "${release_one}" ]] || fail "pointers changed after post-migration failure"
grep -l 'SERVICES_REPLACED=true' "${opt}/apps/shadow-state/deployments/"*"${release_two}.env" >/dev/null || fail "post-migration failure record lacks SERVICES_REPLACED=true"
run "${bin}/deploy-release" "${release_two}" --approval qa-fix-forward
[[ "$(cat "${opt}/apps/shadow-releases/current")" == "${release_two}" ]] || fail "fix-forward pointers"
pass "evidence gate, failed-migration isolation, post-migration failure reporting, fix-forward and schema-compatible coordinated rollback without down migrations"

step "AI via MCP switches from the env file (TASK-069P)"
set_mcp_env() {
  sed -i -E '/^[[:space:]]*(export[[:space:]]+)?MCP_/d' "${env_file}"
  local pair
  for pair in "$@"; do printf '%s\n' "${pair}" >>"${env_file}"; done
}
latest_record() { find "${opt}/apps/shadow-state/deployments" -name "*-${release_two}.env" | sort | tail -n 1; }
# The backend environment holds secrets: match exact lines, never print it.
backend_env_has() {
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
    "$(compose_release "${dir_two}" ps --quiet backend)" | grep -qx "$1"
}
set_mcp_env MCP_ENABLED=yes
expect_failure "an invalid MCP switch blocks deployment" 'MCP_ENABLED must be true or false' \
  "${bin}/deploy-release" "${release_two}" --approval qa-mcp-invalid
expect_failure "check-host reports an invalid MCP switch" 'MCP_ENABLED must be true or false' \
  "${bin}/check-host" --allow-os-mismatch
# Compose reads these forms too, and the backend takes yes, 1 and on as true.
set_mcp_env 'export MCP_ENABLED=yes'
expect_failure "an export-prefixed MCP switch blocks deployment" 'MCP_ENABLED must be a plain MCP_ENABLED=<value> line' \
  "${bin}/deploy-release" "${release_two}" --approval qa-mcp-export
set_mcp_env '  MCP_CHANGE_SET_REVIEW_ENABLED=1'
expect_failure "check-host reports an indented MCP switch" 'MCP_CHANGE_SET_REVIEW_ENABLED must be a plain' \
  "${bin}/check-host" --allow-os-mismatch
set_mcp_env 'MCP_OAUTH_MAX_CLIENTS: 20000'
expect_failure "a KEY: value MCP cap blocks deployment" 'MCP_OAUTH_MAX_CLIENTS must be a plain' \
  "${bin}/deploy-release" "${release_two}" --approval qa-mcp-colon
set_mcp_env
# A release whose Compose file sets a backend MCP value itself, simulated by an
# override on top of the QA override.
mcp_override="${qa_root}/qa-override-mcp.yml"
set_release_mcp() {
  awk -v line="$1" '{ print } /^  backend:$/ { backend = 1 } backend && /^    environment:$/ { print "      " line; backend = 0 }' \
    "${override}" >"${mcp_override}"
}
set_release_mcp 'MCP_ENABLED: "yes"'
expect_failure "a rendered MCP switch other than true or false blocks deployment" 'only true or false and a positive whole number are allowed' \
  env SHADOW_COMPOSE_OVERRIDE_FILE="${mcp_override}" "${bin}/deploy-release" "${release_two}" --approval qa-mcp-rendered
set_mcp_env MCP_ENABLED=true MCP_OAUTH_MAX_CLIENTS=20000
expect_failure "turning MCP on needs its own approval" 'needs --mcp-approval' \
  "${bin}/deploy-release" "${release_two}" --approval qa-mcp-on
run op deploy RELEASE="${release_two}" APPROVAL=qa-mcp-on MCP_APPROVAL=qa-mcp-approval
record="$(latest_record)"
grep -qx 'MCP_ENABLED=true' "${record}" && grep -qx 'MCP_APPROVAL=qa-mcp-approval' "${record}" \
  && grep -qx 'MCP_OAUTH_MAX_CLIENTS=20000' "${record}" || fail "MCP enablement record"
backend_env_has MCP_ENABLED=true && backend_env_has MCP_OAUTH_MAX_CLIENTS=20000 \
  || fail "backend did not get the MCP settings from the env file"
set_mcp_env MCP_ENABLED=true MCP_CHANGE_SET_REVIEW_ENABLED=true
expect_failure "turning MCP change-set review on needs its own approval" 'needs --mcp-approval' \
  "${bin}/deploy-release" "${release_two}" --approval qa-review-on
run "${bin}/deploy-release" "${release_two}" --approval qa-review-on --mcp-approval qa-review-approval
backend_env_has MCP_CHANGE_SET_REVIEW_ENABLED=true || fail "backend did not get the review switch"
run "${bin}/deploy-release" "${release_two}" --approval qa-mcp-unchanged
grep -q '^MCP_APPROVAL=' "$(latest_record)" && fail "an unchanged MCP state recorded an MCP approval"
set_mcp_env
run "${bin}/deploy-release" "${release_two}" --approval qa-mcp-off
grep -qx 'MCP_ENABLED=false' "$(latest_record)" || fail "MCP disable record"
backend_env_has MCP_ENABLED=false && backend_env_has MCP_CHANGE_SET_REVIEW_ENABLED=false \
  || fail "backend kept MCP on after the switch was removed"
status_output="$("${bin}/ops-status" 2>&1)" || fail "ops-status"
grep -q 'deployed: MCP_ENABLED=false' <<<"${status_output}" || fail "ops-status MCP state"
# A release built before TASK-069P pins MCP off and ignores the env file:
# deploying it keeps MCP off, needs no MCP approval and warns.
set_release_mcp 'MCP_ENABLED: "false"'
set_mcp_env MCP_ENABLED=true
pinned_output="$(env SHADOW_COMPOSE_OVERRIDE_FILE="${mcp_override}" "${bin}/deploy-release" "${release_two}" --approval qa-mcp-pinned 2>&1)" \
  || { printf '%s\n' "${pinned_output}" | tee -a "${log_file}" | tail -n 20 >&2; fail "deploying a release that pins MCP off"; }
printf '%s\n' "${pinned_output}" >>"${log_file}"
grep -q 'ignores the MCP settings' <<<"${pinned_output}" || fail "no warning for a release that ignores the env file"
grep -qx 'MCP_ENABLED=false' "$(latest_record)" && ! grep -q '^MCP_APPROVAL=' "$(latest_record)" \
  || fail "record of a release that pins MCP off"
backend_env_has MCP_ENABLED=false || fail "a release that pins MCP off got MCP_ENABLED from the env file"
set_mcp_env
pass "MCP switches and client cap come from the env file; turning MCP or its review on needs --mcp-approval, an unchanged state or a disable does not"

step "Secret leakage scan"
all_logs="$(cat "${log_file}"; for id in $(docker ps --all --quiet); do docker logs "${id}" 2>&1; done)"
for secret in "${db_password}" "${client_secret}" "${key_passphrase}" qa-bootstrap-admin@example.test; do
  grep -qF "${secret}" <<<"${all_logs}" && fail "a synthetic secret appeared in logs"
done
for kind in BACKEND FRONTEND; do
  docker history --no-trunc "$(release_value "${dir_one}" "${kind}_IMAGE_ID")" | grep -qF -e "${db_password}" -e "${client_secret}" && fail "secret in image history"
done
pass "synthetic secrets absent from QA, container logs and image history"

printf '\nTASK-059G/E/H1/H3 production runtime, first-install runbook, Git-free source and server Makefile QA passed. Tools: %s; Compose %s.\n' \
  "$(docker version --format 'Engine {{.Server.Version}}')" "$(docker compose version --short)"
