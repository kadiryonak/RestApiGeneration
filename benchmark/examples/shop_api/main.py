"""Shop API: a small REST API (users and orders) used as a system under test."""

from fastapi import FastAPI

from routers import orders, users

app = FastAPI(title="Shop API", version="1.0.0",
              description="Users and orders. A small example service for test generation.")
app.include_router(users.router)
app.include_router(orders.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
