from types import SimpleNamespace

import pytest

from recycleguard.contracts.workflow import BudgetLimits
from recycleguard.investigation import evaluation_budgets, resolve_budgets

CONFIG = SimpleNamespace(max_total_tokens=16384, max_model_calls=12)


def test_model_backed_runs_get_the_frozen_budget_and_reject_overrides():
    assert resolve_budgets(CONFIG, None) == evaluation_budgets(CONFIG)
    assert evaluation_budgets(CONFIG).max_model_calls == 12
    with pytest.raises(ValueError, match="frozen evaluation budget"):
        resolve_budgets(CONFIG, BudgetLimits(max_model_calls=3))


def test_only_a_pinned_configuration_lowers_the_call_cap():
    forced = SimpleNamespace(max_total_tokens=16384, max_model_calls=2)
    assert resolve_budgets(forced, None).max_model_calls == 2
    assert (
        evaluation_budgets(forced).max_total_tokens == evaluation_budgets(CONFIG).max_total_tokens
    )
    with pytest.raises(ValueError, match="frozen evaluation budget"):
        resolve_budgets(forced, BudgetLimits(max_model_calls=2))


def test_the_configured_cap_cannot_exceed_the_evaluation_cap(tmp_path):
    from pydantic import ValidationError

    from recycleguard.local_model import LocalModelConfig
    from tests.unit.test_local_model import configuration

    model = tmp_path / "model"
    model.mkdir()
    fields = configuration(
        (None, "http://127.0.0.1:9/v1/completions", model), tmp_path
    ).model_dump()
    assert fields["max_model_calls"] == 12
    assert LocalModelConfig(**{**fields, "max_model_calls": 2}).max_model_calls == 2
    for invalid in (0, 13):
        with pytest.raises(ValidationError):
            LocalModelConfig(**{**fields, "max_model_calls": invalid})


def test_scripted_runs_may_override():
    assert resolve_budgets(None, None) == BudgetLimits()
    assert resolve_budgets(None, BudgetLimits(max_model_calls=7)).max_model_calls == 7
