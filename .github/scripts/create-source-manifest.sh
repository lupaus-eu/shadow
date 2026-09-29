#!/usr/bin/env bash
# Export one exact commit and write its source manifest (TASK-059H1, ADR-013).
# Runs only where Git exists: the GitHub runner and local QA. The server never
# runs Git; schatten-receive verifies the delivered files against this manifest.
#
# Usage: create-source-manifest.sh --commit <40-char SHA> --ref <ref> --run-id <digits> --output <new or empty folder>
#   Run from inside the repository. Writes the tracked files of the commit plus
#   <output>/SOURCE_MANIFEST and prints SOURCE_COMMIT= and SOURCE_MANIFEST_SHA256=.
#   The manifest is byte-identical for the same commit, ref and run ID.

set -Eeuo pipefail
export LC_ALL=C

die() {
  printf 'ERROR: create-source-manifest: %s\n' "$*" >&2
  exit 1
}

commit="" ref="" run_id="" output=""
while (( $# > 0 )); do
  (( $# >= 2 )) || die "$1 needs a value"
  case "$1" in
    --commit) commit="$2" ;;
    --ref) ref="$2" ;;
    --run-id) run_id="$2" ;;
    --output) output="$2" ;;
    *) die "Unknown argument $1" ;;
  esac
  shift 2
done
[[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || die "--commit must be a 40-character commit SHA"
[[ "${ref}" =~ ^refs/[A-Za-z0-9._/-]+$ ]] || die "--ref must be a full ref such as refs/heads/main"
[[ "${run_id}" =~ ^[0-9]{1,20}$ ]] || die "--run-id must be the numeric workflow run ID"
[[ -n "${output}" ]] || die "--output is required"
[[ "$(git rev-parse --verify --quiet "${commit}^{commit}")" == "${commit}" ]] \
  || die "${commit} is not a commit in this repository"

mkdir -p "${output}"
[[ -z "$(ls -A "${output}")" ]] || die "${output} must be new or empty"

# Every tracked file with its Git mode; symlinks and submodules are refused
# because the receiver accepts regular files only.
entries=()
while IFS= read -r -d '' record; do
  path="${record#*$'\t'}"
  case "${record%% *}" in
    100644) mode=644 ;;
    100755) mode=755 ;;
    120000) die "symlink ${path} is not allowed in delivered source" ;;
    160000) die "submodule ${path} is not allowed in delivered source" ;;
    *) die "unsupported tree entry ${record%%$'\t'*} for ${path}" ;;
  esac
  # Same rule as schatten-receive: no spaces, quotes, backslashes or control characters.
  [[ "${path}" =~ ^[A-Za-z0-9._@#%+=,~-]+(/[A-Za-z0-9._@#%+=,~-]+)*$ ]] \
    || die "tracked path ${path@Q} has characters the manifest does not allow"
  [[ "${path}" != SOURCE_MANIFEST ]] || die "a tracked SOURCE_MANIFEST would collide with the manifest"
  entries+=("${mode} ${path}")
done < <(git ls-tree -r -z --full-tree "${commit}")
(( ${#entries[@]} > 0 )) || die "${commit} has no tracked files"

git archive --format=tar "${commit}" | tar -x -C "${output}"
[[ -z "$(find "${output}" -mindepth 1 ! -type f ! -type d -print -quit)" ]] \
  || die "the export contains a non-regular file"
# export-ignore/export-subst attributes must not make the export differ from the tree.
diff <(printf '%s\n' "${entries[@]#* }" | sort) \
  <(cd "${output}" && find . -type f | sed 's#^\./##' | sort) >/dev/null \
  || die "the git archive export does not match the tracked files of ${commit}"

manifest="${output}/SOURCE_MANIFEST"
{
  printf 'SOURCE_MANIFEST_VERSION=1\n'
  printf 'SOURCE_COMMIT=%s\n' "${commit}"
  printf 'SOURCE_REF=%s\n' "${ref}"
  printf 'SOURCE_DATE_EPOCH=%s\n' "$(git show -s --format=%ct "${commit}")"
  printf 'SOURCE_RUN_ID=%s\n' "${run_id}"
  printf 'SOURCE_FILE_COUNT=%s\n' "${#entries[@]}"
  for entry in "${entries[@]}"; do
    path="${entry#* }"
    hash="$(sha256sum <"${output}/${path}")"
    printf '%s %s %s\n' "${entry%% *}" "${hash%% *}" "${path}"
  done | sort -t ' ' -k 3
} >"${manifest}"

printf 'SOURCE_COMMIT=%s\n' "${commit}"
printf 'SOURCE_MANIFEST_SHA256=%s\n' "$(sha256sum <"${manifest}" | cut -d ' ' -f 1)"
