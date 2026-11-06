#!/bin/sh
# Weekly release-aware Docker cleanup (ADR-013). Runs inside the hardened
# cleanup-runner container, which is the only runner with Docker socket access.
#
# Scope, all older than CLEANUP_RETENTION_DAYS (default 7):
#   - exited/dead containers without the eu.lupaus.shadow.retain=true label
#   - dangling images and shadow-backend/shadow-frontend release images,
#     except images referenced by any release record or any container
#   - BuildKit build cache
# Never touches volumes, networks, running containers, other repositories'
# tagged images or host files, and never uses `docker system prune`.
#
# --dry-run (default) lists candidates; --apply removes them. Exit codes:
# 0 completed, 1 failed, 64 usage, 75 skipped because the maintenance lock is
# held by a release, build, backup or restore.

set -eu

mode="${1:---dry-run}"
case "${mode}" in
  --dry-run|--apply) ;;
  *)
    echo "Usage: docker-cleanup.sh [--dry-run|--apply]" >&2
    exit 64
    ;;
esac

days="${CLEANUP_RETENTION_DAYS:-7}"
case "${days}" in
  ''|*[!0-9]*|0) echo "CLEANUP_RETENTION_DAYS must be a positive integer" >&2; exit 64 ;;
esac
# Test-only override so fixtures can be aged without waiting a week.
now="${SHADOW_CLEANUP_NOW_EPOCH:-$(date -u +%s)}"
cutoff=$((now - days * 86400))
failures=0
removed_containers=0
removed_images=0

log() {
  printf '%s cleanup %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

abort() {
  log "status=failed mode=${mode} error=\"$1\""
  exit 1
}

to_epoch() {
  stamp="${1%%.*}"
  stamp="${stamp%Z}"
  date -u -D '%Y-%m-%dT%H:%M:%S' -d "${stamp}" +%s 2>/dev/null
}

[ -r /locks/maintenance.lock ] || abort "maintenance lock file is missing"
exec 9</locks/maintenance.lock
if ! flock -n -x 9; then
  log "status=skipped mode=${mode} reason=\"maintenance lock held by a release, build, backup or restore\""
  exit 75
fi

docker version --format '{{.Server.Version}}' >/dev/null 2>&1 \
  || abort "Docker API is not reachable through the mounted socket"

log "status=started mode=${mode} retention_days=${days} cutoff_epoch=${cutoff}"

# Listings are captured explicitly: a failed listing must fail the run, never
# look like an empty candidate or protection list.
stopped="$(docker ps --all --no-trunc --quiet --filter status=exited --filter status=dead)" \
  || abort "could not list stopped containers"

# Containers.
for id in ${stopped}; do
  if ! info="$(docker inspect --format '{{.Name}}|{{index .Config.Labels "eu.lupaus.shadow.retain"}}|{{.State.FinishedAt}}' "${id}")"; then
    failures=$((failures + 1))
    continue
  fi
  name="${info%%|*}"
  rest="${info#*|}"
  retain="${rest%%|*}"
  finished="${rest#*|}"
  if [ "${retain}" = "true" ]; then
    log "keep container=${name} reason=retain-label"
    continue
  fi
  if ! finished_epoch="$(to_epoch "${finished}")"; then
    log "error container=${name} reason=unparseable-finish-time"
    failures=$((failures + 1))
    continue
  fi
  [ "${finished_epoch}" -lt "${cutoff}" ] || continue
  if [ "${mode}" = "--dry-run" ]; then
    log "candidate container=${name} finished_at=${finished}"
  elif docker rm "${id}" >/dev/null; then
    log "removed container=${name}"
    removed_containers=$((removed_containers + 1))
  else
    log "error container=${name} reason=remove-failed"
    failures=$((failures + 1))
  fi
done

# Protected images: every non-retired release record and every container.
protected="$(mktemp)"
releases=0
for record in /releases/*/release.env; do
  [ -f "${record}" ] || continue
  releases=$((releases + 1))
  grep -E '^(BACKEND|FRONTEND)_IMAGE_ID=sha256:[0-9a-f]{64}$' "${record}" | cut -d= -f2 >>"${protected}" || true
done
all_containers="$(docker ps --all --no-trunc --quiet)" \
  || abort "could not list containers for image protection"
for id in ${all_containers}; do
  docker inspect --format '{{.Image}}' "${id}" >>"${protected}" 2>/dev/null || failures=$((failures + 1))
done

# Images.
images="$(docker images --no-trunc --format '{{.ID}} {{.Repository}}')" \
  || abort "could not list images"
for id in $(printf '%s\n' "${images}" \
  | awk '$2 == "<none>" || $2 == "shadow-backend" || $2 == "shadow-frontend" { print $1 }' \
  | sort -u); do
  if grep -qx "${id}" "${protected}"; then
    log "keep image=${id} reason=release-or-container"
    continue
  fi
  if ! created="$(docker image inspect --format '{{.Created}}' "${id}")" \
    || ! created_epoch="$(to_epoch "${created}")"; then
    log "error image=${id} reason=inspect-failed"
    failures=$((failures + 1))
    continue
  fi
  [ "${created_epoch}" -lt "${cutoff}" ] || continue
  tags="$(docker image inspect --format '{{range .RepoTags}}{{.}} {{end}}' "${id}" \
    | tr ' ' '\n' | grep -E '^shadow-(backend|frontend):' || true)"
  if [ -n "${tags}" ] && [ "${releases}" -eq 0 ]; then
    log "keep image=${id} reason=no-release-records"
    continue
  fi
  if [ "${mode}" = "--dry-run" ]; then
    log "candidate image=${id} created_at=${created} tags=\"$(echo ${tags})\""
    continue
  fi
  targets="${tags:-${id}}"
  image_failed=0
  for target in ${targets}; do
    docker image rm "${target}" >/dev/null || image_failed=1
  done
  if [ "${image_failed}" -eq 0 ]; then
    log "removed image=${id}"
    removed_images=$((removed_images + 1))
  else
    log "error image=${id} reason=remove-failed"
    failures=$((failures + 1))
  fi
done
rm -f "${protected}"

# Build cache (Docker applies `until` against real time).
if [ "${mode}" = "--dry-run" ]; then
  build_cache="$(docker system df --format '{{if eq .Type "Build Cache"}}{{.Size}} total, {{.Reclaimable}} reclaimable{{end}}' | tr -d '\n')"
  log "candidate build_cache=\"${build_cache}\" until=$((days * 24))h"
elif build_cache="$(docker builder prune --force --filter "until=$((days * 24))h" 2>&1)"; then
  log "removed build_cache=\"$(printf '%s\n' "${build_cache}" | tail -n 1)\""
else
  log "error build_cache reason=prune-failed"
  failures=$((failures + 1))
fi

if [ "${failures}" -gt 0 ]; then
  log "status=failed mode=${mode} containers_removed=${removed_containers} images_removed=${removed_images} failures=${failures}"
  exit 1
fi
log "status=completed mode=${mode} containers_removed=${removed_containers} images_removed=${removed_images} failures=0"
