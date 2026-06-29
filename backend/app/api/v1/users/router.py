from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v1.users import service
from app.api.v1.users.schemas import UserCreateRequest, UserPatchRequest, UserResponse
from app.core.database import get_db_session

router = APIRouter(prefix="/users", tags=["users"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=list[UserResponse])
def list_users(session: SessionDependency) -> list[UserResponse]:
    return service.list_users(session)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    session: SessionDependency,
) -> UserResponse:
    return service.get_user(session, user_id)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    session: SessionDependency,
) -> UserResponse:
    return service.create_user(session, payload)


@router.patch("/{user_id}", response_model=UserResponse)
def patch_user(
    user_id: int,
    payload: UserPatchRequest,
    session: SessionDependency,
) -> UserResponse:
    return service.patch_user(session, user_id, payload)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    session: SessionDependency,
) -> Response:
    service.soft_delete_user(session, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
