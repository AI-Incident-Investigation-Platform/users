from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query, Request, Response, status

from src.api.users.dto import ProfileChanges
from src.api.users.service import UserService
from src.api.users.v1.cookies import cache_avatar
from src.api.users.v1.schemas import (
    ProfileUpdateRequest,
    Username,
    UsernameAvailabilityResponse,
    UserResponse,
    UsersLookupResponse,
    UsersPageResponse,
)
from src.config import cfg
from src.core.db.dto.user import WorkingHours
from src.core.security.dto import CurrentUser

router = APIRouter(prefix="/users", tags=["users"], route_class=DishkaRoute)


@router.get("/me")
async def get_me(
    service: FromDishka[UserService], current_user: FromDishka[CurrentUser]
) -> UserResponse:
    user = await service.get_me(current_user)
    return UserResponse.model_validate(user, from_attributes=True)


@router.patch("/me")
async def update_me(
    body: ProfileUpdateRequest,
    service: FromDishka[UserService],
    current_user: FromDishka[CurrentUser],
) -> UserResponse:
    hours = body.working_hours
    user = await service.update_profile(
        current_user,
        ProfileChanges(
            provided=frozenset(body.model_fields_set),
            username=body.username,
            display_name=body.display_name,
            timezone=body.timezone,
            working_hours=WorkingHours(
                starts_at=hours.starts_at, ends_at=hours.ends_at, days=tuple(hours.days)
            )
            if hours
            else None,
        ),
    )
    return UserResponse.model_validate(user, from_attributes=True)


@router.put("/me/avatar")
async def set_avatar(
    request: Request, service: FromDishka[UserService], current_user: FromDishka[CurrentUser]
) -> UserResponse:
    """Тело запроса — сама картинка, Content-Type — её формат."""
    user = await service.set_avatar(
        current_user, await request.body(), request.headers.get("content-type")
    )
    return UserResponse.model_validate(user, from_attributes=True)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(
    service: FromDishka[UserService], current_user: FromDishka[CurrentUser]
) -> None:
    await service.delete_avatar(current_user)


@router.get("/username-availability")
async def check_username(
    username: Annotated[Username, Query()],
    service: FromDishka[UserService],
    current_user: FromDishka[CurrentUser],
) -> UsernameAvailabilityResponse:
    available = await service.is_username_available(current_user, username)
    return UsernameAvailabilityResponse(username=username, available=available)


@router.get("/lookup")
async def lookup_users(
    ids: Annotated[list[UUID], Query(min_length=1, max_length=cfg.search.lookup_max_ids)],
    service: FromDishka[UserService],
    current_user: FromDishka[CurrentUser],
) -> UsersLookupResponse:
    users = await service.lookup(ids)
    return UsersLookupResponse(
        items=[UserResponse.model_validate(user, from_attributes=True) for user in users]
    )


@router.get("")
async def search_users(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    service: FromDishka[UserService],
    current_user: FromDishka[CurrentUser],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=cfg.search.max_limit)] = cfg.search.default_limit,
) -> UsersPageResponse:
    page = await service.search(q, cursor, limit)
    return UsersPageResponse(
        items=[UserResponse.model_validate(user, from_attributes=True) for user in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{user_id}")
async def get_user(
    user_id: UUID, service: FromDishka[UserService], current_user: FromDishka[CurrentUser]
) -> UserResponse:
    user = await service.get_user(user_id)
    return UserResponse.model_validate(user, from_attributes=True)


@router.get("/{user_id}/avatar", response_class=Response)
async def get_avatar(
    user_id: UUID, service: FromDishka[UserService], current_user: FromDishka[CurrentUser]
) -> Response:
    avatar = await service.get_avatar(user_id)
    response = Response(content=avatar.data, media_type=avatar.content_type)
    cache_avatar(response)
    return response
