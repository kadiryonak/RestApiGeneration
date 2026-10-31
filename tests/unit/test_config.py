from pathlib import Path

import pytest

from restgen.config import load_settings
from restgen.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]


def test_repository_config_loads() -> None:
    settings = load_settings(ROOT)
    assert settings.root == ROOT
    assert settings.paths.results_dir == ROOT / "results"
    assert len(settings.repetitions.seeds) >= 5
    assert settings.evaluation.success_status_min == 200
    assert "authorization" in settings.proxy.redact_headers
    assert settings.dabc_hs.population_size == 50
    assert settings.dabc_hs.size_factors == (0.25, 0.75, 0.5)


def test_override_replaces_value_with_toml_literal() -> None:
    settings = load_settings(
        ROOT,
        overrides=["budget.max_time_seconds=600", "repetitions.seeds=[1, 2]"],
    )
    assert settings.budget.max_time_seconds == 600
    assert settings.repetitions.seeds == (1, 2)


def test_override_of_nested_tool_section() -> None:
    settings = load_settings(ROOT, overrides=['tools.schemathesis.extra_args=["--no-shrink"]'])
    assert settings.schemathesis.extra_args == ("--no-shrink",)


@pytest.mark.parametrize(
    "override",
    ["budget.unknown=1", "nosuch.key=1", "budget.max_time_seconds", "budget.max_time_seconds=x y"],
)
def test_bad_override_is_rejected(override: str) -> None:
    with pytest.raises(ConfigError):
        load_settings(ROOT, overrides=[override])


@pytest.mark.parametrize(
    "override",
    [
        "budget.max_time_seconds=0",
        "budget.max_time_seconds=true",
        "evaluation.success_status_min=700",
        "evaluation.rerun_count=0",
        "repetitions.seeds=[]",
        "method.dabc_hs.size_factors=[]",
        "method.dabc_hs.mutation_rate=1.1",
    ],
)
def test_invalid_values_are_rejected(override: str) -> None:
    with pytest.raises(ConfigError):
        load_settings(ROOT, overrides=[override])


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path)


def test_to_dict_is_json_friendly() -> None:
    data = load_settings(ROOT).to_dict()
    assert data["paths"]["results_dir"].endswith("results")
    assert isinstance(data["repetitions"]["seeds"], list)
