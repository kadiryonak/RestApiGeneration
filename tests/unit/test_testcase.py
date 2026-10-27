from pathlib import Path
from typing import Any

import pytest

from restgen.core.representation.action import HttpAction
from restgen.core.representation.inputs import (
    EnumInput,
    IntegerInput,
    ObjectInput,
    StringInput,
)
from restgen.core.representation.templates import OperationTemplate, build_templates
from restgen.core.representation.testcase import TestCase
from restgen.core.representation.values import (
    ABSENT,
    EnumValue,
    IntegerValue,
    NullValue,
    ObjectValue,
    OptionalValue,
    ResponseRef,
    StringValue,
    placeholder,
)
from restgen.errors import UnresolvedReferenceError
from restgen.openapi import OpenApiSpec

SHOP_OPENAPI = Path(__file__).parents[2] / "benchmark/examples/shop_api/openapi.json"


@pytest.fixture(scope="module")
def shop() -> dict[str, OperationTemplate]:
    return {t.key: t for t in build_templates(OpenApiSpec.load(SHOP_OPENAPI))}


def _user_body(template: OperationTemplate, age: int, role: str | None) -> ObjectValue:
    body = placeholder(template.body.spec) if template.body else None
    assert isinstance(body, ObjectValue)
    for name, text in (("name", "Ali"), ("email", "ali@shop.com"), ("country", "US")):
        field = body.fields[name]
        assert isinstance(field, StringValue)
        field.value = text
    age_value = body.fields["age"]
    assert isinstance(age_value, IntegerValue)
    age_value.value = age
    role_value = body.fields["role"]
    assert isinstance(role_value, OptionalValue) and isinstance(role_value.inner, EnumValue)
    if role is not None:
        role_value.present = True
        role_value.inner.index = role_value.inner.spec.values.index(role)
    return body


def test_shop_templates(shop: dict[str, OperationTemplate]) -> None:
    create_user = shop["POST /users"]
    assert create_user.body is not None and create_user.body.required
    spec = create_user.body.spec
    assert isinstance(spec, ObjectInput) and spec.schema_name == "UserCreate"
    props = {p.name: p for p in spec.properties}
    assert props["age"].spec == IntegerInput(minimum=0, maximum=130)
    assert props["role"].spec == EnumInput(values=("USER", "ADMIN")) and not props["role"].required
    get_user = shop["GET /users/{user_id}"]
    assert [i.key for i in get_user.inputs] == ["path:user_id"]
    # FastAPI writes `coupon: str | None` as anyOf [string, null]: a nullable string
    order = shop["POST /orders"].body
    assert order is not None and isinstance(order.spec, ObjectInput)
    coupon = {p.name: p.spec for p in order.spec.properties}["coupon"]
    assert coupon == StringInput(nullable=True)


def test_placeholder_is_complete_and_leaves_optional_parts_out(
    shop: dict[str, OperationTemplate],
) -> None:
    action = HttpAction.placeholder(shop["POST /users"])
    request = action.to_request()
    assert request.method == "POST" and request.path == "/users"
    assert request.media_type == "application/json"
    assert request.body == {"name": "aa", "email": "", "age": 0, "country": ""}

    listing = HttpAction.placeholder(shop["GET /users"]).to_request()
    assert listing.query == () and listing.body is ABSENT and listing.media_type is None


def test_sequence_with_response_reference(shop: dict[str, OperationTemplate]) -> None:
    create = HttpAction(
        shop["POST /users"], body=_user_body(shop["POST /users"], age=17, role="ADMIN")
    )
    user_id = shop["GET /users/{user_id}"].inputs[0]
    fetch = HttpAction(
        shop["GET /users/{user_id}"],
        {user_id.key: ResponseRef(user_id.spec, action=0, path="$.id")},
    )
    case = TestCase([create, fetch])
    case.validate()

    first = case.request(0, [])
    assert first.body["age"] == 17 and first.body["role"] == "ADMIN"
    second = case.request(1, [{"id": 7, "name": "Ali"}])
    assert second.path == "/users/7"
    assert case.describe()[1] == {
        "operation": "GET /users/{user_id}",
        "path:user_id": {"from_action": 0, "path": "$.id"},
    }
    with pytest.raises(UnresolvedReferenceError):
        case.request(1, [{"detail": "users must be at least 18"}])


def test_copy_is_independent(shop: dict[str, OperationTemplate]) -> None:
    create = shop["POST /users"]
    case = TestCase([HttpAction(create, body=_user_body(create, 30, None))])
    clone = case.copy()
    body = clone.actions[0].body
    assert isinstance(body, ObjectValue) and isinstance(body.fields["age"], IntegerValue)
    body.fields["age"].value = 99
    assert case.request(0, []).body["age"] == 30
    assert clone.request(0, []).body["age"] == 99


def test_validate_rejects_forward_references(shop: dict[str, OperationTemplate]) -> None:
    user_id = shop["GET /users/{user_id}"].inputs[0]
    fetch = HttpAction(
        shop["GET /users/{user_id}"], {user_id.key: ResponseRef(user_id.spec, 0, "$.id")}
    )
    with pytest.raises(ValueError, match="refers to action 0"):
        TestCase([fetch]).validate()


def test_action_rejects_unknown_inputs(shop: dict[str, OperationTemplate]) -> None:
    with pytest.raises(ValueError, match="no input"):
        HttpAction(shop["GET /users"], {"query:nope": NullValue(StringInput())})
    with pytest.raises(ValueError, match="no request body"):
        HttpAction(shop["GET /users"], body=NullValue(StringInput()))


@pytest.mark.parametrize(
    ("path", "body", "expected"),
    [
        ("$", 5, 5),
        ("$.id", {"id": 3}, 3),
        ("$.items[1].id", {"items": [{"id": 1}, {"id": 2}]}, 2),
    ],
)
def test_response_paths(path: str, body: Any, expected: Any) -> None:
    assert ResponseRef(IntegerInput(), 0, path).render([body]) == expected


@pytest.mark.parametrize("path", ["id", "$id", "$.items[x]"])
def test_malformed_response_paths(path: str) -> None:
    with pytest.raises(ValueError):
        ResponseRef(IntegerInput(), 0, path)


def test_query_rendering_of_scalars_and_arrays(shop: dict[str, OperationTemplate]) -> None:
    listing = shop["GET /users"]
    keys = {i.name: i for i in listing.inputs}
    action = HttpAction(
        listing,
        {
            keys["min_age"].key: placeholder(keys["min_age"].spec),
            keys["country"].key: OptionalValue(NullValue(keys["country"].spec), present=True),
        },
    )
    assert action.to_request().query == (("country", "null"), ("min_age", "0"))
