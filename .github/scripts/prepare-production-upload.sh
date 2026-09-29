#!/usr/bin/env bash
# Prepare the "Deploy to production" upload (TASK-059H2, ADR-013).
# Runs on the GitHub runner (and in verify-upload-gate.sh) from inside the
# repository: exports GITHUB_SHA with its SOURCE_MANIFEST into <output>, writes
# source_manifest_sha256 to GITHUB_OUTPUT and the commit, run ID and manifest
# SHA-256 to GITHUB_STEP_SUMMARY. Reads no secrets.
#
# Usage: prepare-production-upload.sh <output folder>
# Environment: GITHUB_SHA, GITHUB_REF, GITHUB_RUN_ID, GITHUB_OUTPUT,
#   GITHUB_STEP_SUMMARY

set -Eeuo pipefail
export LC_ALL=C

die() {
  printf 'ERROR: prepare-production-upload: %s\n' "$*" >&2
  exit 1
}

(( $# == 1 )) || die "usage: prepare-production-upload.sh <output folder>"
output="$1"
[[ "${GITHUB_REF:-}" == refs/heads/main ]] || die "only refs/heads/main may be delivered, not ${GITHUB_REF:-<unset>}"
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || die "GITHUB_SHA must be a 40-character commit SHA"
[[ -n "${GITHUB_OUTPUT:-}" && -n "${GITHUB_STEP_SUMMARY:-}" ]] \
  || die "GITHUB_OUTPUT and GITHUB_STEP_SUMMARY are required"

result="$("$(dirname "$0")/create-source-manifest.sh" --commit "${GITHUB_SHA}" \
  --ref "${GITHUB_REF}" --run-id "${GITHUB_RUN_ID:-}" --output "${output}")"
commit="$(sed -n 's/^SOURCE_COMMIT=//p' <<<"${result}")"
digest="$(sed -n 's/^SOURCE_MANIFEST_SHA256=//p' <<<"${result}")"
[[ "${commit}" == "${GITHUB_SHA}" ]] || die "the manifest commit ${commit} is not ${GITHUB_SHA}"
[[ "${digest}" =~ ^[0-9a-f]{64}$ ]] || die "no manifest SHA-256 was printed"

printf 'source_manifest_sha256=%s\n' "${digest}" >>"${GITHUB_OUTPUT}"
cat >>"${GITHUB_STEP_SUMMARY}" <<EOF
## Deploy to production: source upload

| Field | Value |
| --- | --- |
| Commit | \`${commit}\` |
| Ref | \`${GITHUB_REF}\` |
| Run ID | \`${GITHUB_RUN_ID}\` |
| Upload folder | \`/opt/apps/schatten-upload/${commit}\` |
| Manifest SHA-256 | \`${digest}\` |

Accept on the host only after this run has succeeded, as \`deploy\`:
\`schatten-receive ${digest}\`
EOF
printf 'SOURCE_COMMIT=%s\nSOURCE_MANIFEST_SHA256=%s\n' "${commit}" "${digest}"
