from pydantic import BaseModel, Field


class OrderCreate(BaseModel):
    user_id: int
    product: str = Field(description="One of the products in the catalogue")
    quantity: int = Field(ge=1, le=100)
    coupon: str | None = None


class Order(BaseModel):
    id: int
    user_id: int
    user_name: str
    product: str
    quantity: int
    unit_price: float
    total: float
    status: str  # "open" or "cancelled"
