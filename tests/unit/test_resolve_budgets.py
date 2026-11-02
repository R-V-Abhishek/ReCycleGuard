from types import SimpleNamespace

import pytest

from recycleguard.contracts.workflow import BudgetLimits
from recycleguard.investigation import evaluation_budgets, resolve_budgets

CONFIG = SimpleNamespace(max_total_tokens=16384)


def test_model_backed_runs_get_the_frozen_budget_and_reject_overrides():
    assert resolve_budgets(CONFIG, None) == evaluation_budgets(CONFIG)
    with pytest.raises(ValueError, match="frozen evaluation budget"):
        resolve_budgets(CONFIG, BudgetLimits(max_model_calls=3))


def test_scripted_runs_may_override():
    assert resolve_budgets(None, None) == BudgetLimits()
    assert resolve_budgets(None, BudgetLimits(max_model_calls=7)).max_model_calls == 7
