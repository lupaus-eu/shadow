"""From a verified MCP token to the signed-in customer User Account (ADR-0038).

The MCP issuer is an alias of the issuer accounts are stored under: the subject is the
same in both Authentik providers, so the lookup uses the canonical issuer. MCP never
creates an account, and only customer accounts may use it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcp_server.settings import McpSettings
from app.models import AccountClass, UserAccount


class NotSignedUp(Exception):
    """The token's subject has no customer account in Shadow."""


def customer_account(session: Session, settings: McpSettings, subject: str) -> UserAccount:
    account = session.scalar(
        select(UserAccount).where(
            UserAccount.oidc_issuer == settings.canonical_issuer,
            UserAccount.oidc_subject == subject,
        )
    )
    if account is None or account.account_class != AccountClass.CUSTOMER.value:
        raise NotSignedUp
    return account
