# Run by configure.sh through `ak shell` (a blueprint cannot change tenants): people may not
# change their own email or username, because the verified address links a person to their
# Shadow account (ADR-017), and impersonation is off, because support access to a company is
# explicit and approved by the customer (step 7 of the SaaS plan), not an Authentik feature.
from authentik.tenants.models import Tenant

for tenant in Tenant.objects.all():
    tenant.default_user_change_email = False
    tenant.default_user_change_username = False
    tenant.impersonation = False
    tenant.save()
    print(f"Tenant settings applied to {tenant.name}")
