from pathlib import Path

import pytest

from restgen.errors import ConfigError, MeasurementError
from restgen.llm.accounting import (
    BudgetExceededError,
    ModelPrice,
    PricingTable,
    UsageLedger,
    usage_summary,
)

PRICE = ModelPrice(
    "acme",
    "m1",
    input=2.0,
    output=8.0,
    cached_input=0.5,
    source="https://acme.example/pricing",
    checked_on="2026-10-21",
)
TABLE = """
[[price]]
provider = "acme"
model = "m1"
input = 2.0
cached_input = 0.5
output = 8.0
source = "https://acme.example/pricing"
checked_on = "2026-10-21"
"""


def test_cost_uses_cache_discount() -> None:
    # 1M input of which 400k cached, 100k output
    assert PRICE.cost(1_000_000, 400_000, 100_000) == pytest.approx(1.2 + 0.2 + 0.8)
    no_cache = ModelPrice("p", "m", 1.0, 1.0, None, "https://x", "2026-01-01")
    assert no_cache.cost(1_000_000, 500_000, 0) == pytest.approx(1.0)


def test_pricing_table_requires_source_and_date(tmp_path: Path) -> None:
    path = tmp_path / "pricing.toml"
    path.write_text(TABLE)
    assert PricingTable.load(path).get("acme", "m1") == PRICE
    for broken in (
        TABLE.replace('source = "https://acme.example/pricing"\n', ""),
        TABLE.replace("https://acme.example/pricing", "my notes"),
        TABLE.replace("2026-10-21", "last week"),
    ):
        path.write_text(broken)
        with pytest.raises(ConfigError):
            PricingTable.load(path)
    assert (
        PricingTable.load(Path(__file__).parents[2] / "configs" / "pricing.toml").get("acme", "m1")
        is None
    )


def test_ledger_records_and_summarises(tmp_path: Path) -> None:
    path = tmp_path / "llm_usage.jsonl"
    ledger = UsageLedger(path, PricingTable([PRICE]))
    first = ledger.record(
        provider="acme",
        model="m1",
        purpose="scout.construct",
        input_tokens=1000,
        cached_input_tokens=200,
        output_tokens=300,
        duration_ms=850.0,
        request_sha256="a" * 64,
        temperature=0.2,
        seed=42,
    )
    assert first.call_id == 1
    assert first.cost_usd == pytest.approx((800 * 2 + 200 * 0.5 + 300 * 8) / 1e6)
    assert first.price is not None and first.price["checked_on"] == "2026-10-21"
    ledger.record(
        provider="acme",
        model="m1",
        purpose="employed.neighbour",
        input_tokens=500,
        output_tokens=50,
        duration_ms=150.0,
        request_sha256="b" * 64,
        attempt=2,
        status="error",
    )
    summary = usage_summary(path)
    assert summary is not None
    assert summary["llm_calls"] == 2
    assert summary["llm_retries"] == 1
    assert summary["llm_failed_calls"] == 1
    assert summary["llm_input_tokens"] == 1500
    assert summary["latency_ms_median"] == 500.0
    assert summary["by_purpose"]["scout.construct"]["calls"] == 1
    assert summary["usd"] == pytest.approx(ledger.spent_usd)

    resumed = UsageLedger(path, PricingTable([PRICE]))  # continues numbering after a resume
    assert (
        resumed.record(
            provider="acme",
            model="m1",
            purpose="x",
            input_tokens=1,
            output_tokens=1,
            duration_ms=1.0,
            request_sha256="c",
        ).call_id
        == 3
    )


def test_unpriced_model_makes_total_unknown(tmp_path: Path) -> None:
    path = tmp_path / "llm_usage.jsonl"
    ledger = UsageLedger(path, PricingTable([PRICE]))
    ledger.record(
        provider="acme",
        model="m1",
        purpose="x",
        input_tokens=10,
        output_tokens=10,
        duration_ms=1.0,
        request_sha256="a",
    )
    call = ledger.record(
        provider="other",
        model="m9",
        purpose="x",
        input_tokens=10,
        output_tokens=10,
        duration_ms=1.0,
        request_sha256="b",
    )
    assert call.cost_usd is None
    summary = usage_summary(path)
    assert summary is not None and summary["usd"] is None and summary["unpriced_calls"] == 1
    assert usage_summary(tmp_path / "none.jsonl") is None


def test_budget_and_invalid_counts(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path / "u.jsonl", PricingTable([PRICE]), max_usd=0.001)
    ledger.check_budget()
    ledger.record(
        provider="acme",
        model="m1",
        purpose="x",
        input_tokens=1000,
        output_tokens=1000,
        duration_ms=1.0,
        request_sha256="a",
    )
    with pytest.raises(BudgetExceededError):
        ledger.check_budget()
    with pytest.raises(MeasurementError):
        ledger.record(
            provider="acme",
            model="m1",
            purpose="x",
            input_tokens=10,
            cached_input_tokens=20,
            output_tokens=1,
            duration_ms=1.0,
            request_sha256="a",
        )
