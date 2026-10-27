from fastapi import APIRouter, Query, Response

from models.user import User, UserCreate
from services import users

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", status_code=201, response_model=User,
             responses={400: {"description": "Too young"}, 403: {"description": "Country or admin rule"},
                        409: {"description": "Email already registered"}})
def create_user(data: UserCreate) -> User:
    return users.create_user(data)


@router.get("", response_model=list[User])
def list_users(country: str | None = None, min_age: int = Query(default=0, ge=0)) -> list[User]:
    return users.list_users(country, min_age)


@router.get("/{user_id}", response_model=User, responses={404: {"description": "Not found"}})
def get_user(user_id: int) -> User:
    return users.get_user(user_id)


@router.delete("/{user_id}", status_code=204,
               responses={404: {"description": "Not found"}, 409: {"description": "Open orders"}})
def delete_user(user_id: int) -> Response:
    users.delete_user(user_id)
    return Response(status_code=204)
