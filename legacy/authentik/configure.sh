#!/bin/sh
set -eu

# Applying the blueprints takes close to a minute, so skip it when nothing that
# feeds them has changed since the last successful run: this script, the custom
# and development blueprints, the blueprints shipped in the image (a new Authentik
# version changes them), and the environment values the blueprints read. The
# fingerprint is kept in the authentik_media volume; without the volume it lives
# in the stopped container. Set AUTHENTIK_CONFIG_FORCE=true to apply regardless,
# for example after the Authentik database was recreated but the volume was not.
marker=/media/.shadow-config-applied
fingerprint=$(
    {
        cat /config/configure.sh /config/*.py /blueprints/custom/*.yaml /blueprints/custom/*.css \
            /blueprints/dev/*.yaml /blueprints/dev/*.py \
            /blueprints/example/flows-enrollment-email-verification.yaml \
            /blueprints/example/flows-recovery-email-mfa-verification.yaml 2>/dev/null
        printenv CONFIG_IMAGE_VERSION OIDC_CLIENT_ID OIDC_CLIENT_SECRET OIDC_REDIRECT_URI FRONTEND_URL AUTHENTIK_ENROLLMENT_OPEN MCP_OIDC_CLIENT_ID MCP_OIDC_CLIENT_SECRET AUTHENTIK_DEV_USER_PASSWORD || true
    } | sha256sum | cut -d' ' -f1
)

if [ "${AUTHENTIK_CONFIG_FORCE:-false}" != "true" ] && [ -r "$marker" ] && [ "$(cat "$marker")" = "$fingerprint" ]; then
    echo "Authentik configuration unchanged since the last run; skipping (AUTHENTIK_CONFIG_FORCE=true applies it anyway)."
    exit 0
fi

ak apply_blueprint \
    /blueprints/example/flows-enrollment-email-verification.yaml \
    /blueprints/example/flows-recovery-email-mfa-verification.yaml

ak apply_blueprint /blueprints/custom/shadow-identity-flows.yaml
ak apply_blueprint /blueprints/custom/shadow-application.yaml
ak apply_blueprint /blueprints/custom/shadow-mcp-application.yaml
ak apply_blueprint /blueprints/custom/shadow-brand.yaml
ak shell < /config/apply-tenant-settings.py

# Development users exist only where the blueprints/dev directory is mounted
# (the local Compose project); production never mounts it.
if [ -d /blueprints/dev ]; then
    for blueprint in /blueprints/dev/*.yaml; do
        [ -e "$blueprint" ] && ak apply_blueprint "$blueprint"
    done
    ak shell < /blueprints/dev/provision-dev-totp.py
fi

# `ak apply_blueprint` can exit 0 without applying, so check that the essentials exist
# before the success is recorded (a failed run is retried).
ak shell < /config/verify-config.py

# Record success only after every blueprint applied; a failed run is retried.
echo "$fingerprint" > "$marker" 2>/dev/null || echo "Could not record the configuration fingerprint at $marker; the next run applies it again."
