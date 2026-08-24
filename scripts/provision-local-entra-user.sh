#!/usr/bin/env bash
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly BASE_ENV_FILE="${REPOSITORY_ROOT}/.env"
readonly AUTHENTIK_ENV_FILE="${REPOSITORY_ROOT}/.env.authentik.local"
readonly ENTRA_ENV_FILE="${1:-${REPOSITORY_ROOT}/.env.entra.local}"

for required_file in "${BASE_ENV_FILE}" "${AUTHENTIK_ENV_FILE}" "${ENTRA_ENV_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    printf 'Missing required local environment file: %s\n' "${required_file}" >&2
    exit 1
  fi
done

set -a
# shellcheck disable=SC1090
source "${ENTRA_ENV_FILE}"
set +a

if [[ -z "${ENTRA_TEST_USER_EMAIL:-}" ]]; then
  printf 'ENTRA_TEST_USER_EMAIL is required.\n' >&2
  exit 1
fi
if [[ "${ENTRA_TEST_USER_ROLE:-}" != consultant && "${ENTRA_TEST_USER_ROLE:-}" != admin ]]; then
  printf 'ENTRA_TEST_USER_ROLE must be consultant or admin.\n' >&2
  exit 1
fi

docker compose \
  --project-directory "${REPOSITORY_ROOT}" \
  --env-file "${BASE_ENV_FILE}" \
  --env-file "${AUTHENTIK_ENV_FILE}" \
  --env-file "${ENTRA_ENV_FILE}" \
  -f "${REPOSITORY_ROOT}/docker-compose.yml" \
  -f "${REPOSITORY_ROOT}/docker-compose.entra.yml" \
  exec -T database \
  sh -c 'psql -v ON_ERROR_STOP=1 -v entra_email="$1" -v entra_role="$2" -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  _ "${ENTRA_TEST_USER_EMAIL}" "${ENTRA_TEST_USER_ROLE}" <<'SQL'
INSERT INTO users (name, email, role)
SELECT 'Entra Development User', :'entra_email', :'entra_role'
WHERE NOT EXISTS (
    SELECT 1
    FROM users
    WHERE lower(trim(email)) = lower(trim(:'entra_email'))
      AND deleted_time IS NULL
);
SQL

printf 'The active Schatten allowlist contains the configured Entra test user.\n'
