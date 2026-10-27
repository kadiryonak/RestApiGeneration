from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
    age: int = Field(ge=0, le=130)
    country: str = Field(pattern=r"^[A-Z]{2}$", description="ISO country code, e.g. TR, US")
    role: Role = Role.USER


class User(UserCreate):
    id: int
