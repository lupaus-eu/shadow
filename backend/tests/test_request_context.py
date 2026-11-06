from uuid import uuid4

from sqlalchemy import text

from app.database import (
    RequestContext,
    create_database_engine,
    create_session_factory,
    transaction_session,
)


def test_transaction_sets_trusted_request_context(database_url: str) -> None:
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    context = RequestContext(
        user_account_id=uuid4(),
        organization_id=uuid4(),
        support_access_id=uuid4(),
    )

    with transaction_session(session_factory, context) as session:
        values = session.execute(
            text(
                """
                SELECT
                    current_setting('app.current_user_account_id', true),
                    current_setting('app.current_organization_id', true),
                    current_setting('app.current_support_access_id', true)
                """
            )
        ).one()

    assert values == (
        str(context.user_account_id),
        str(context.organization_id),
        str(context.support_access_id),
    )
