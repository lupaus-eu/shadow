from datetime import UTC, datetime
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.users.models import User
from app.api.v1.users.schemas import (
    UserCreateRequest,
    UserPatchRequest,
    UserResponse,
    UserRole,
)


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.user_id,
        name=user.name,
        email=user.email,
        role=cast(UserRole, user.role),
    )


def list_users(session: Session) -> list[UserResponse]:
    users = session.scalars(
        select(User).where(User.deleted_time.is_(None)).order_by(User.user_id),
    ).all()

    return [to_user_response(user) for user in users]


def get_user(session: Session, user_id: int) -> UserResponse:
    return to_user_response(_get_active_user(session, user_id))


def create_user(session: Session, payload: UserCreateRequest) -> UserResponse:
    _ensure_email_is_available(session, payload.email)
    user = User(name=payload.name, email=payload.email, role=payload.role)
    session.add(user)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _duplicate_email_exception() from exc

    session.refresh(user)

    return to_user_response(user)


def patch_user(
    session: Session,
    user_id: int,
    payload: UserPatchRequest,
) -> UserResponse:
    user = _get_active_user(session, user_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data:
        user.name = payload.name if payload.name is not None else user.name
    if "role" in update_data:
        user.role = payload.role if payload.role is not None else user.role
    if "email" in update_data and payload.email is not None:
        if payload.email.lower() != user.email.lower():
            _ensure_email_is_available(
                session,
                payload.email,
                excluding_user_id=user.user_id,
            )
        user.email = payload.email

    user.modified_time = datetime.now(UTC)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _duplicate_email_exception() from exc

    session.refresh(user)

    return to_user_response(user)


def soft_delete_user(session: Session, user_id: int) -> None:
    user = _get_active_user(session, user_id)
    now = datetime.now(UTC)

    user.deleted_time = now
    user.modified_time = now
    session.commit()


def _get_active_user(session: Session, user_id: int) -> User:
    user = session.scalar(
        select(User).where(
            User.user_id == user_id,
            User.deleted_time.is_(None),
        ),
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user


def _ensure_email_is_available(
    session: Session,
    email: str,
    excluding_user_id: int | None = None,
) -> None:
    query = select(User.user_id).where(
        func.lower(User.email) == email.lower(),
        User.deleted_time.is_(None),
    )

    if excluding_user_id is not None:
        query = query.where(User.user_id != excluding_user_id)

    if session.scalar(query) is not None:
        raise _duplicate_email_exception()


def _duplicate_email_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="An active user with this email already exists.",
    )
