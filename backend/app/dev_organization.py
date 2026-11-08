"""Local development only: create an active Organization without Stripe.

    python -m app.dev_organization --email frank@example.com --name "Dev Oy" --seats 5

The user must have signed in once. The command refuses to run with a live Stripe key.
The Stripe identifiers are placeholders, so billing pages that call Stripe will not work.
"""

import argparse
import os
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Organization, OrganizationMembership, OrganizationRole, OrganizationStatus, UserAccount


def create_active_organization(session: Session, *, email: str, name: str, seats: int, now: datetime | None = None) -> Organization:
    user = session.scalar(select(UserAccount).where(UserAccount.email == email.strip().lower(), UserAccount.account_class == "customer"))
    if user is None:
        raise LookupError("no customer account with that email; sign in to Shadow once first")
    now = now or datetime.now(UTC)
    organization = Organization(
        id=uuid4(),
        name=name,
        time_zone="Europe/Helsinki",
        default_locale=user.locale,
        status=OrganizationStatus.ACTIVE.value,
        created_by_user_account_id=user.id,
        billing_name=name,
        billing_email=user.email,
        purchased_seats=seats,
        pending_activation_expires_at=now,
        activated_at=now,
    )
    organization.stripe_customer_id = f"dev_cus_{organization.id.hex}"
    organization.stripe_subscription_id = f"dev_sub_{organization.id.hex}"
    session.add(organization)
    session.flush()
    session.add(OrganizationMembership(id=uuid4(), organization_id=organization.id, user_account_id=user.id, role=OrganizationRole.OWNER.value))
    return organization


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Dev Organization")
    parser.add_argument("--seats", type=int, default=5)
    arguments = parser.parse_args()
    if os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_live"):
        raise SystemExit("refusing to run with a live Stripe key")
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session, session.begin():
        organization = create_active_organization(session, email=arguments.email, name=arguments.name, seats=arguments.seats)
        print(f"Created active Organization {organization.name} ({organization.id}) with {arguments.seats} seats; owner {arguments.email}.")


if __name__ == "__main__":
    main()
