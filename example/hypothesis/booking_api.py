"""A tiny booking REST API with two deliberate bugs, used by test_06_rest_api.py."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Example booking API", version="1.0.0")
PRICES = {"standard": 99.99, "deluxe": 149.99, "suite": 299.99}
BOOKINGS: dict[int, dict[str, object]] = {}


class BookingRequest(BaseModel):
    guest_name: str = Field(min_length=2, max_length=100)
    room_type: str  # the schema does not list the valid room types
    nights: int = Field(gt=0, le=365)


@app.post("/bookings", status_code=201)
def create_booking(booking: BookingRequest) -> dict[str, object]:
    price = PRICES[booking.room_type]  # BUG 1: unknown room type -> KeyError -> 500
    booking_id = len(BOOKINGS) + 1
    BOOKINGS[booking_id] = {"id": booking_id, **booking.model_dump(), "total": price}
    return BOOKINGS[booking_id]


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: int) -> dict[str, object]:
    if booking_id not in BOOKINGS:
        raise HTTPException(status_code=404, detail="no such booking")
    return BOOKINGS[booking_id]


@app.get("/stats")
def stats(days: int = 7) -> dict[str, float]:
    return {"per_day": len(BOOKINGS) / days}  # BUG 2: days=0 -> ZeroDivisionError -> 500
