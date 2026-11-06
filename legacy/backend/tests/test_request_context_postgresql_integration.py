from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import RequestContext, transaction_session


def test_transaction_session_runs_as_application_role_with_context(
    schema_session_factory: sessionmaker[Session],
) -> None:
    tenant_id = uuid4()
    with transaction_session(
        schema_session_factory, RequestContext(user_id=101, tenant_id=tenant_id)
    ) as session:
        assert session.scalar(text("SELECT current_user")) == "shadow_app"
        assert (
            session.scalar(text("SELECT current_setting('app.current_user_id')"))
            == "101"
        )
        assert session.scalar(
            text("SELECT current_setting('app.current_tenant_id')")
        ) == str(tenant_id)


def test_role_and_context_do_not_leak_to_the_next_transaction(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with transaction_session(
        schema_session_factory, RequestContext(user_id=101)
    ) as session:
        login_role = session.scalar(text("SELECT session_user"))
    with schema_session_factory() as session:
        assert session.scalar(text("SELECT current_user")) == login_role
        assert not session.scalar(
            text("SELECT current_setting('app.current_user_id', true)")
        )


def test_application_role_can_use_existing_tables(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with transaction_session(schema_session_factory, RequestContext()) as session:
        assert session.scalar(text("SELECT count(*) FROM users")) is not None
        session.execute(
            text(
                "INSERT INTO users (name, role, email) "
                "VALUES ('Probe', 'consultant', 'probe@example.test')"
            )
        )


def test_application_role_has_no_privileges_beyond_data_access(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(ProgrammingError):
        with transaction_session(schema_session_factory, RequestContext()) as session:
            session.execute(text("CREATE TABLE forbidden (id int)"))


def test_application_role_does_not_bypass_row_level_security(
    schema_database_url: str,
) -> None:
    with psycopg.connect(schema_database_url) as connection:
        row = connection.execute(
            "SELECT rolcanlogin, rolbypassrls, rolsuper FROM pg_roles "
            "WHERE rolname = 'shadow_app'"
        ).fetchone()
    assert row == (False, False, False)


def test_role_and_context_do_not_leak_after_a_rollback_on_the_same_connection(
    schema_database_url: str,
) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(
        schema_database_url.replace("postgresql://", "postgresql+psycopg://"),
        pool_size=1,
        max_overflow=0,
    )
    factory = sessionmaker(bind=engine, autoflush=False)
    first_pid: object = None
    try:
        with pytest.raises(RuntimeError):
            with transaction_session(factory, RequestContext(user_id=7)) as session:
                first_pid = session.scalar(text("SELECT pg_backend_pid()"))
                raise RuntimeError("boom")
        with factory() as session:
            assert session.scalar(text("SELECT pg_backend_pid()")) == first_pid
            assert session.scalar(text("SELECT current_user")) != "shadow_app"
            assert not session.scalar(
                text("SELECT current_setting('app.current_user_id', true)")
            )
    finally:
        engine.dispose()


def test_committing_inside_the_block_fails_instead_of_dropping_the_role(
    schema_session_factory: sessionmaker[Session],
) -> None:
    from sqlalchemy.exc import InvalidRequestError

    with pytest.raises(InvalidRequestError):
        with transaction_session(schema_session_factory, RequestContext()) as session:
            session.commit()
            session.scalar(text("SELECT 1"))


def test_unset_tenant_context_yields_no_rows_with_the_documented_expression(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with transaction_session(schema_session_factory, RequestContext()) as session:
        value = session.scalar(
            text(
                "SELECT NULLIF(current_setting('app.current_tenant_id', true), '')"
                "::uuid"
            )
        )
    assert value is None
