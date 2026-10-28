"""Provider-usage limits survive replay and reject invalid financial metadata."""

import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest

from recycleguard.application import command_context
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a06_workflow import workflow as workflow
from tests.support.workflow import assess, plan


def test_usage_budget_stop_survives_crash_before_turn_intent(workflow):
    with workflow([replace(plan(), usage={"total_tokens": 2049}), assess()]) as env:
        state = env.drive(env.start(), until={"INVESTIGATING"})
        env.cases.kernel.connection.execute("""CREATE TRIGGER fail_usage_turn
            BEFORE INSERT ON operation_intents
            WHEN NEW.intent_json LIKE '%"event_type":"graph.turn"%'
            BEGIN SELECT RAISE(ABORT,'crash before turn intent'); END""")
        with pytest.raises(sqlite3.Error):
            env.advance(state)
        assert not env.lookup.calls
        env.cases.kernel.connection.execute("DROP TRIGGER fail_usage_turn")
        env.clock.now += timedelta(seconds=1)
        env.restart()
        restored = env.runner.resume(
            command_context(env.context.actor), state.run_id, None, capability=env.capability
        )
        final = env.drive(restored)
        assert final.status == "FAILED" and final.stop_reason == "BUDGET_EXHAUSTED"
        assert final.budget.observed_tokens == 2049
        assert final.budget.usage_known_calls == 1
        assert len(env.port.calls) == 1
        assert not env.lookup.calls


@pytest.mark.parametrize("cost", ["NaN", "sNaN", "Infinity", "-Infinity", "-0.01", "invalid"])
def test_invalid_provider_cost_is_an_explicit_failure_before_tool_execution(workflow, cost):
    with workflow([replace(plan(), usage={"total_tokens": 100, "cost_usd": cost})]) as env:
        state = env.drive(env.start())
        assert state.status == "FAILED" and state.stop_reason == "PROVIDER_FAILURE"
        assert state.budget.observed_cost_usd is None
        assert not env.lookup.calls


def test_finite_zero_cost_is_known_without_being_invented(workflow):
    steps = [
        replace(plan(), usage={"total_tokens": 100, "cost_usd": "0"}),
        replace(assess(), usage={"total_tokens": 80, "cost_usd": "0.001"}),
    ]
    with workflow(steps) as env:
        state = env.drive(env.start())
        assert state.status == "AWAITING_REVIEW"
        assert state.budget.observed_tokens == 180
        assert state.budget.observed_cost_usd == "0.001"
        assert state.budget.cost_known_calls == 2


def test_another_approved_corpus_cannot_replace_the_frozen_case_pin(workflow):
    from recycleguard.application import local_review_application
    from recycleguard.contracts.artifacts import SnapshotRef
    from recycleguard.contracts.snapshots import SnapshotPublication, SnapshotReview
    from recycleguard.local_session import initialize_reviewer

    with workflow([]) as env:
        password = "synthetic-corpus-review-password"
        initialize_reviewer(env.settings.data_root, "human:corpus_test", password)
        with local_review_application(env.settings, password) as args:
            cases, human_context, human_cap, actor, service_cap = args
            original = cases.snapshots.get(env.spec.corpus_snapshot)
            published = cases.publish_corpus(
                command_context(actor),
                SnapshotPublication(
                    scope_id="corpus:initial",
                    snapshot_id="snapshot:other_corpus_draft",
                    snapshot_kind="CORPUS",
                    expected_head=original.snapshot_id,
                    membership_blob=original.membership_blob,
                    membership_digest=original.membership_digest,
                    coverage_blob=original.coverage_blob,
                    source_receipt_ids=original.source_receipt_ids,
                ),
                capability=service_cap,
            )
            assert published.status == "SUCCESS"
            approved = cases.review_snapshot(
                human_context,
                SnapshotReview(
                    scope_id="corpus:initial",
                    target_snapshot_id=published.output.snapshot_id,
                    target_membership_digest=published.output.membership_digest,
                    expected_head=published.output.snapshot_id,
                    new_snapshot_id="snapshot:other_corpus_approved",
                    decision="APPROVE",
                    reason="Synthetic test fixture; another approved revision of the same corpus.",
                ),
                capability=human_cap,
            )
            assert approved.status == "SUCCESS"
        env.spec = env.spec.model_copy(
            update={
                "corpus_snapshot": SnapshotRef(
                    snapshot_id=approved.output.snapshot_id,
                    membership_digest=approved.output.membership_digest,
                )
            }
        )
        with pytest.raises(ValueError, match="corpus differs from the frozen case"):
            env.start()
        assert not env.port.calls and not env.preflight.calls
