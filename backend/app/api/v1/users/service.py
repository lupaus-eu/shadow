from datetime import UTC, datetime
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.users.models import User
from app.api.v1.users.schemas import (
    UserCreateRequest,
    UserPatchRequest,
    UserResponse,
    UserRole,
)


def to_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.user_id, name=user.name, role=cast(UserRole, user.role))


def list_users(session: Session) -> list[UserResponse]:
    users = session.scalars(
        select(User).where(User.deleted_time.is_(None)).order_by(User.user_id),
    ).all()

    return [to_user_response(user) for user in users]


def get_user(session: Session, user_id: int) -> UserResponse:
    return to_user_response(_get_active_user(session, user_id))


def create_user(session: Session, payload: UserCreateRequest) -> UserResponse:
    user = User(name=payload.name, role=payload.role)
    session.add(user)
    session.commit()
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

    user.modified_time = datetime.now(UTC)
    session.commit()
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
