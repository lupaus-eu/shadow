#!/usr/bin/env bash
# Verifies the release health gate in deploy/lib/common.sh without Docker:
# docker, compose_release and sleep are stubbed and replay a state sequence.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=deploy/lib/common.sh
source "${repo_root}/deploy/lib/common.sh"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

sleep() { :; }
compose_release() { [[ -s "${work}/container" ]] && cat "${work}/container"; return 0; }
# State samples come from a file because wait_for_healthy calls docker in a
# command substitution; the last state repeats once the sequence runs out.
docker() {
  local format="$3"
  if [[ "${format}" == *State.Status* ]]; then
    local sample
    sample="$(<"${work}/samples")"
    printf '%s\n' "$((sample + 1))" >"${work}/samples"
    sed -n "$((sample + 1))p" "${work}/states" | grep . || tail -n 1 "${work}/states"
  else
    [[ "${format}" != *Output* ]] || { echo "probe output requested" >&2; return 1; }
    printf 'probe exit=-1 start=t1 end=t2\nprobe exit=0 start=t3 end=t4\n\n'
  fi
}

repeat() { local i; for ((i = 0; i < $2; i++)); do printf '%s\n' "$1"; done; }

# expect <name> <pass|fail> <samples> <attempts>, with states on stdin.
expect() {
  local name="$1" outcome="$2" samples="$3" attempts="$4" result=pass
  cat >"${work}/states"
  printf '0\n' >"${work}/samples"
  wait_for_healthy release worker "${attempts}" 2>"${work}/log" || result=fail
  if [[ "${result}" != "${outcome}" || "$(<"${work}/samples")" != "${samples}" ]]; then
    echo "${name}: expected ${outcome} after ${samples} samples, got ${result} after $(<"${work}/samples")" >&2
    cat "${work}/log" >&2
    exit 1
  fi
  if [[ "${outcome}" == fail ]]; then
    grep -q 'worker probe exit=-1 start=t1 end=t2$' "${work}/log" \
      && grep -q 'worker probe exit=0 start=t3 end=t4$' "${work}/log" \
      && [[ "$(grep -c 'probe exit=' "${work}/log")" == 2 ]] \
      || { echo "${name}: probe exit codes not logged" >&2; cat "${work}/log" >&2; exit 1; }
  fi
}

printf 'container-id\n' >"${work}/container"
{ repeat running/unhealthy 14; echo running/healthy; } | expect "transient unhealthy recovers" pass 15 60
echo running/unhealthy | expect "persistent unhealthy fails" fail 15 60
printf 'running/starting\nexited/unhealthy\n' | expect "exited fails at once" fail 2 60
{ repeat running/unhealthy 14; echo running/starting; repeat running/unhealthy 14; echo running/healthy; } \
  | expect "non-unhealthy sample resets the count" pass 30 60
echo running/starting | expect "never healthy fails after the attempts" fail 5 5

: >"${work}/container"
printf '0\n' >"${work}/samples"
if wait_for_healthy release worker 3 2>"${work}/log"; then
  echo "missing container: expected failure" >&2
  exit 1
fi
grep -q 'did not become healthy (state missing)$' "${work}/log" && ! grep -q 'probe exit=' "${work}/log" \
  || { echo "missing container: unexpected log" >&2; cat "${work}/log" >&2; exit 1; }

echo "Release health gate tolerates a transient unhealthy status, fails persistent unhealthy, exited and missing services, and logs only probe exit codes and times."
