from fastapi import APIRouter

from models.order import Order, OrderCreate
from services import orders

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", status_code=201, response_model=Order,
             responses={400: {"description": "Unknown product"},
                        403: {"description": "Total above 1000 by a non-admin"},
                        404: {"description": "No such user"},
                        409: {"description": "Quantity limit"}})
def create_order(data: OrderCreate) -> Order:
    return orders.create_order(data)


@router.get("/{order_id}", response_model=Order, responses={404: {"description": "Not found"}})
def get_order(order_id: int) -> Order:
    return orders.get_order(order_id)


@router.post("/{order_id}/cancel", response_model=Order,
             responses={404: {"description": "Not found"}, 409: {"description": "Cancelled"}})
def cancel_order(order_id: int) -> Order:
    return orders.cancel_order(order_id)
