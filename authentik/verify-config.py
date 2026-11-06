# Sanity check run by configure.sh through `ak shell` after the blueprints (ADR-017): the
# strong-authentication pieces and the web application must exist, or the run fails and is
# retried instead of recorded as done.
import sys

from authentik.core.models import Application
from authentik.flows.models import Flow, FlowStageBinding
from authentik.stages.authenticator_validate.models import AuthenticatorValidateStage
from authentik.tenants.models import Tenant

problems = []

if not Application.objects.filter(slug="shadow").exists():
    problems.append("application shadow is missing")

enrollment = Flow.objects.filter(slug="default-enrollment-flow").first()
if enrollment is None:
    problems.append("default-enrollment-flow is missing")
else:
    mfa = FlowStageBinding.objects.filter(
        target=enrollment, order=90, stage__name="default-authentication-mfa-validation"
    )
    if not mfa.exists():
        problems.append("the second-factor stage is not bound to enrollment")
    invitation = FlowStageBinding.objects.filter(
        target=enrollment, order=0, stage__name="shadow-enrollment-invitation"
    )
    if not invitation.exists():
        problems.append("the invitation stage is not bound to enrollment")

stage = AuthenticatorValidateStage.objects.filter(name="default-authentication-mfa-validation").first()
if stage is None or stage.not_configured_action != "configure":
    problems.append("sign-in does not force a second factor to be configured")

tenants = list(Tenant.objects.all())
if not tenants or any(t.impersonation or t.default_user_change_email for t in tenants):
    problems.append("tenant settings are not applied (impersonation or own email change is on)")

if problems:
    print("Authentik configuration check failed: " + "; ".join(problems), file=sys.stderr)
    sys.exit(1)
print("Authentik configuration check passed.")
