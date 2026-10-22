# Shop API

A small FastAPI service (users and orders) to use as a system under test. State is kept in
memory, so every start begins empty.

```
shop_api/
├── main.py              app + /health
├── routers/             HTTP layer: users.py, orders.py
├── services/            business rules: users.py, orders.py, store.py (in-memory data)
├── models/              request/response models (pydantic): user.py, order.py
├── export_openapi.py    writes openapi.json
├── openapi.json         the OpenAPI 3.1 document (also served at /openapi.json)
└── requirements.txt
```

## Run it

```bash
cd benchmark/examples/shop_api
uv venv --python 3.12 .venv                                # once
uv pip install --python .venv/bin/python -r requirements.txt   # once

.venv/bin/uvicorn main:app --port 8000                     # start (Ctrl+C stops it)
```

Then, in a browser:
- http://127.0.0.1:8000/docs — interactive documentation (Swagger UI): every endpoint,
  its parameters and responses; "Try it out" sends real requests
- http://127.0.0.1:8000/openapi.json — the raw OpenAPI document

Or from another terminal:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/users -H 'Content-Type: application/json' \
     -d '{"name":"John","email":"john@test.com","age":30,"country":"US"}'
curl http://127.0.0.1:8000/users/1
```

Regenerate `openapi.json` after changing the code: `.venv/bin/python export_openapi.py`.

## Endpoints and rules

| Endpoint | Responses |
|---|---|
| `GET /health` | 200 |
| `POST /users` | 201 created · 400 age < 18 · 403 country `TR` and age < 21 · 409 e-mail already registered · 422 invalid body |
| `GET /users?country=&min_age=` | 200 list (filtered) |
| `GET /users/{user_id}` | 200 · 404 |
| `DELETE /users/{user_id}` | 204 · 404 · 409 user has open orders |
| `POST /orders` | 201 · 400 unknown product · 404 no such user · 409 more than 10 laptops · 422 invalid body |
| `GET /orders/{order_id}` | 200 · 404 |
| `POST /orders/{order_id}/cancel` | 200 · 404 · 409 already cancelled |

Products: `book` 12.5, `phone` 499.0, `laptop` 950.0. Coupons: `WELCOME10` (10 %), `VIP20` (20 %).

## Known faults (ground truth)

Planted on purpose, so that a test generator's fault detection can be checked:

1. **Unknown coupon → 500.** `POST /orders` with a coupon that is not in the list raises a
   `KeyError` (`services/orders.py`); it should be a 4xx.
2. **Order of a deleted user → 500 (needs a sequence).** Create a user, create an order,
   cancel the order, delete the user, then `GET /orders/{id}`: `KeyError` when the user
   name is looked up. A single request cannot trigger it.

The 409 laptop check in `create_order` runs after the price and coupon are computed, so a
request with more than 10 laptops and an unknown coupon hits fault 1 first.
