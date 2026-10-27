from fastapi import HTTPException

from models.order import Order, OrderCreate
from services.store import ORDERS, USERS, next_id

CATALOGUE = {"book": 12.5, "phone": 499.0, "laptop": 950.0}
COUPONS = {"WELCOME10": 0.10, "VIP20": 0.20}
ADMIN_ONLY_TOTAL = 1000.0  # orders above this total need an ADMIN user


def _to_order(record: dict[str, object]) -> Order:
    user = USERS[record["user_id"]]  # type: ignore[index]
    return Order(**record, user_name=user["name"])  # type: ignore[arg-type]


def create_order(data: OrderCreate) -> Order:
    if data.user_id not in USERS:
        raise HTTPException(status_code=404, detail="no such user")
    if data.product not in CATALOGUE:
        raise HTTPException(status_code=400, detail="unknown product")
    unit_price = CATALOGUE[data.product]
    total = unit_price * data.quantity
    if data.coupon is not None:
        total = total * (1 - COUPONS[data.coupon])
    if data.quantity > 10 and data.product == "laptop":
        raise HTTPException(status_code=409, detail="at most 10 laptops per order")
    if total > ADMIN_ONLY_TOTAL and USERS[data.user_id]["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="orders above 1000 need an ADMIN user")
    order_id = next_id("order")
    ORDERS[order_id] = {
        "id": order_id,
        "user_id": data.user_id,
        "product": data.product,
        "quantity": data.quantity,
        "unit_price": unit_price,
        "total": round(total, 2),
        "status": "open",
    }
    return _to_order(ORDERS[order_id])


def get_order(order_id: int) -> Order:
    if order_id not in ORDERS:
        raise HTTPException(status_code=404, detail="no such order")
    return _to_order(ORDERS[order_id])


def cancel_order(order_id: int) -> Order:
    if order_id not in ORDERS:
        raise HTTPException(status_code=404, detail="no such order")
    if ORDERS[order_id]["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="order already cancelled")
    ORDERS[order_id]["status"] = "cancelled"
    return _to_order(ORDERS[order_id])
