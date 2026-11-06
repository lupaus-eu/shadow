"""Keep the ID token of a session until logout, for OIDC RP-initiated logout.

Authentik accepts ``post_logout_redirect_uri`` only together with
``id_token_hint``. The token is cleared when the session is revoked.

Revision ID: 0029
Revises: 0028
"""

import sqlalchemy as sa
from alembic import op


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("id_token_hint", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_sessions", "id_token_hint")
