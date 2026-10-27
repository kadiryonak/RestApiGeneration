from fastapi import HTTPException

from models.user import Role, User, UserCreate
from services.store import ORDERS, USERS, next_id


def create_user(data: UserCreate) -> User:
    if data.age < 18:
        raise HTTPException(status_code=400, detail="users must be at least 18")
    if data.country == "TR" and data.age < 21:
        raise HTTPException(status_code=403, detail="users in TR must be at least 21")
    if data.role == Role.ADMIN and not data.email.endswith("@shop.com"):
        raise HTTPException(status_code=403, detail="admins need a @shop.com e-mail")
    if any(user["email"] == data.email for user in USERS.values()):
        raise HTTPException(status_code=409, detail="email already registered")
    user_id = next_id("user")
    USERS[user_id] = {"id": user_id, **data.model_dump(mode="json")}
    return User(**USERS[user_id])


def get_user(user_id: int) -> User:
    if user_id not in USERS:
        raise HTTPException(status_code=404, detail="no such user")
    return User(**USERS[user_id])


def list_users(country: str | None, min_age: int) -> list[User]:
    users = [User(**u) for u in USERS.values()]
    if country is not None:
        users = [u for u in users if u.country == country]
    return [u for u in users if u.age >= min_age]


def delete_user(user_id: int) -> None:
    if user_id not in USERS:
        raise HTTPException(status_code=404, detail="no such user")
    if any(o["user_id"] == user_id and o["status"] == "open" for o in ORDERS.values()):
        raise HTTPException(status_code=409, detail="user has open orders")
    del USERS[user_id]
