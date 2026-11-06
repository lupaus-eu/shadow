# Development only (ADR-017): give the seeded development users a confirmed TOTP device with
# the RFC 6238 test secret, so that sign-in keeps its second factor without a phone.
# Run by configure.sh through `ak shell`; idempotent.
from authentik.core.models import User
from authentik.stages.authenticator_totp.models import TOTPDevice

KEY = "3132333435363738393031323334353637383930"  # "12345678901234567890" in hex

for username in ("dev-admin", "dev-consultant"):
    user = User.objects.filter(username=username).first()
    if user is None:
        continue
    TOTPDevice.objects.update_or_create(
        user=user,
        name="Development TOTP",
        defaults={"key": KEY, "confirmed": True, "digits": 6},
    )
    print(f"TOTP device ready for {username}")
