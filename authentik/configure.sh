#!/bin/sh
set -eu

# Applying the blueprints takes close to a minute, so skip it when nothing that
# feeds them has changed since the last successful run: this script, the custom
# blueprints, the blueprints shipped in the image (a new Authentik version
# changes them), and the environment values the blueprints read. The fingerprint
# is kept in the authentik_media volume (production); without the volume it lives
# in the stopped container. Set AUTHENTIK_CONFIG_FORCE=true to apply regardless,
# for example after the Authentik database was recreated but the volume was not.
marker=/media/.yearclock-config-applied
fingerprint=$(
    {
        cat /config/configure.sh /blueprints/custom/*.yaml /blueprints/custom/*.css \
            /blueprints/example/flows-enrollment-email-verification.yaml \
            /blueprints/example/flows-recovery-email-mfa-verification.yaml 2>/dev/null
        printenv OIDC_CLIENT_ID OIDC_CLIENT_SECRET OIDC_REDIRECT_URI FRONTEND_URL AUTHENTIK_ENROLLMENT_OPEN MCP_OIDC_CLIENT_ID MCP_OIDC_CLIENT_SECRET AUTHENTIK_THEME_CSS_URL || true
    } | sha256sum | cut -d' ' -f1
)

if [ "${AUTHENTIK_CONFIG_FORCE:-false}" != "true" ] && [ -r "$marker" ] && [ "$(cat "$marker")" = "$fingerprint" ]; then
    echo "Authentik configuration unchanged since the last run; skipping (AUTHENTIK_CONFIG_FORCE=true applies it anyway)."
    exit 0
fi

ak apply_blueprint \
    /blueprints/example/flows-enrollment-email-verification.yaml \
    /blueprints/example/flows-recovery-email-mfa-verification.yaml

ak apply_blueprint /blueprints/custom/yearclock-identity-flows.yaml
ak apply_blueprint /blueprints/custom/yearclock-application.yaml
ak apply_blueprint /blueprints/custom/yearclock-mcp-application.yaml
ak apply_blueprint /blueprints/custom/yearclock-brand.yaml

# Record success only after every blueprint applied; a failed run is retried.
echo "$fingerprint" > "$marker" 2>/dev/null || echo "Could not record the configuration fingerprint at $marker; the next run applies it again."
