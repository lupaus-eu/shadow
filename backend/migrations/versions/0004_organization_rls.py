"""Enforce Organization row-level security.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CURRENT_USER = (
    "NULLIF(current_setting('app.current_user_account_id', true), '')::uuid"
)
CURRENT_ORGANIZATION = (
    "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'yearclock_app'
            ) THEN
                EXECUTE 'CREATE ROLE yearclock_app NOLOGIN NOSUPERUSER NOBYPASSRLS';
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT yearclock_app TO CURRENT_USER")
    op.execute("GRANT USAGE ON SCHEMA public TO yearclock_app")
    op.execute(
        """
        REVOKE ALL PRIVILEGES
        ON ALL TABLES IN SCHEMA public
        FROM yearclock_app
        """
    )
    op.execute(
        """
        REVOKE ALL PRIVILEGES
        ON ALL SEQUENCES IN SCHEMA public
        FROM yearclock_app
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE ALL ON TABLES FROM yearclock_app
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE ALL ON SEQUENCES FROM yearclock_app
        """
    )
    table_privileges = {
        "alembic_version": "SELECT",
        "audit_events": "INSERT",
        "outbox_messages": "SELECT, INSERT, UPDATE",
        "background_jobs": "SELECT, INSERT, UPDATE",
        "user_accounts": "SELECT, INSERT, UPDATE",
        "oidc_login_attempts": "SELECT, INSERT, UPDATE, DELETE",
        "user_sessions": "SELECT, INSERT, UPDATE",
        "organizations": "SELECT, INSERT, UPDATE, DELETE",
        "organization_memberships": "SELECT, INSERT, UPDATE, DELETE",
        "yearclocks": "SELECT, INSERT, UPDATE, DELETE",
        "lanes": "SELECT, INSERT, UPDATE, DELETE",
        "stripe_webhook_events": "SELECT, INSERT",
    }
    for table_name, privileges in table_privileges.items():
        op.execute(
            f"GRANT {privileges} ON TABLE {table_name} TO yearclock_app"
        )

    for table_name in (
        "organizations",
        "organization_memberships",
        "yearclocks",
        "lanes",
    ):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")

    op.execute(
        f"""
        CREATE POLICY organizations_select ON organizations
        FOR SELECT
        USING (
            id = {CURRENT_ORGANIZATION}
            OR (
                {CURRENT_ORGANIZATION} IS NULL
                AND (
                    (
                        status IN ('pending_activation', 'expired')
                        AND created_by_user_account_id = {CURRENT_USER}
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM organization_memberships membership
                        WHERE membership.organization_id = organizations.id
                          AND membership.user_account_id = {CURRENT_USER}
                    )
                )
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY organizations_insert ON organizations
        FOR INSERT
        WITH CHECK (
            {CURRENT_ORGANIZATION} IS NULL
            AND status = 'pending_activation'
            AND created_by_user_account_id = {CURRENT_USER}
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY organizations_update ON organizations
        FOR UPDATE
        USING (
            id = {CURRENT_ORGANIZATION}
            OR (
                {CURRENT_ORGANIZATION} IS NULL
                AND status IN ('pending_activation', 'expired')
                AND created_by_user_account_id = {CURRENT_USER}
            )
        )
        WITH CHECK (
            id = {CURRENT_ORGANIZATION}
            OR (
                {CURRENT_ORGANIZATION} IS NULL
                AND status IN ('pending_activation', 'expired')
                AND created_by_user_account_id = {CURRENT_USER}
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY organizations_delete ON organizations
        FOR DELETE
        USING (id = {CURRENT_ORGANIZATION})
        """
    )

    op.execute(
        f"""
        CREATE POLICY organization_memberships_select
        ON organization_memberships
        FOR SELECT
        USING (
            organization_id = {CURRENT_ORGANIZATION}
            OR (
                {CURRENT_ORGANIZATION} IS NULL
                AND user_account_id = {CURRENT_USER}
            )
        )
        """
    )
    for operation in ("INSERT", "UPDATE"):
        using = (
            f"USING (organization_id = {CURRENT_ORGANIZATION})"
            if operation == "UPDATE"
            else ""
        )
        op.execute(
            f"""
            CREATE POLICY organization_memberships_{operation.lower()}
            ON organization_memberships
            FOR {operation}
            {using}
            WITH CHECK (organization_id = {CURRENT_ORGANIZATION})
            """
        )
    op.execute(
        f"""
        CREATE POLICY organization_memberships_delete
        ON organization_memberships
        FOR DELETE
        USING (organization_id = {CURRENT_ORGANIZATION})
        """
    )

    for table_name in ("yearclocks", "lanes"):
        op.execute(
            f"""
            CREATE POLICY {table_name}_select ON {table_name}
            FOR SELECT
            USING (organization_id = {CURRENT_ORGANIZATION})
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table_name}_insert ON {table_name}
            FOR INSERT
            WITH CHECK (organization_id = {CURRENT_ORGANIZATION})
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table_name}_update ON {table_name}
            FOR UPDATE
            USING (organization_id = {CURRENT_ORGANIZATION})
            WITH CHECK (organization_id = {CURRENT_ORGANIZATION})
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table_name}_delete ON {table_name}
            FOR DELETE
            USING (organization_id = {CURRENT_ORGANIZATION})
            """
        )


def downgrade() -> None:
    for policy_name in (
        "organizations_select",
        "organizations_insert",
        "organizations_update",
        "organizations_delete",
    ):
        op.execute(f"DROP POLICY {policy_name} ON organizations")
    for policy_name in (
        "organization_memberships_select",
        "organization_memberships_insert",
        "organization_memberships_update",
        "organization_memberships_delete",
    ):
        op.execute(
            f"DROP POLICY {policy_name} ON organization_memberships"
        )
    for table_name in ("yearclocks", "lanes"):
        for operation in ("select", "insert", "update", "delete"):
            op.execute(
                f"DROP POLICY {table_name}_{operation} ON {table_name}"
            )
    for table_name in (
        "organizations",
        "organization_memberships",
        "yearclocks",
        "lanes",
    ):
        op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
