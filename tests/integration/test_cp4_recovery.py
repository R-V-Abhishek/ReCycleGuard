"""V08 checkpoint integrity and recovery accounting, using real audit persistence."""

import json
import sqlite3

import pytest

from recycleguard.application import command_context
from recycleguard.storage import canonical_json_bytes
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a06_workflow import workflow as workflow
from tests.support.workflow import assess, plan


@pytest.mark.parametrize("corruption", ["envelope_sequence", "future_sequence"])
def test_checkpoint_sequence_disagreement_cannot_change_state_or_dispatch(workflow, corruption):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start(), until={"INVESTIGATING"})
        checkpoint = json.loads(env.cases.kernel.blob_store.get(state.last_checkpoint_ref))
        if corruption == "envelope_sequence":
            checkpoint["last_audit_sequence"] += 1
        else:
            historical = env.runner.store.load(state.run_id).model_copy(
                update={"last_audit_sequence": state.last_audit_sequence + 100}
            )
            checkpoint.update(
                version=historical.version,
                last_audit_sequence=historical.last_audit_sequence,
                state_blob=env.cases.kernel.blob_store.put(
                    canonical_json_bytes(historical.model_dump(mode="json")), "application/json"
                ).model_dump(mode="json"),
            )
        forged = env.cases.kernel.blob_store.put(
            canonical_json_bytes(checkpoint), "application/json"
        )
        # Trusted test corruption: persist the faulty cache reference through the
        # actual CAS/audit path rather than monkeypatching the state loader.
        state = env.runner.store.save(
            env.runner._bound(command_context(env.context.actor), env.spec),
            state.model_copy(update={"last_checkpoint_ref": forged}),
            state.version,
            capability=env.capability,
        )
        with pytest.raises(ValueError, match="checkpoint"):
            env.runner.resume(
                command_context(env.context.actor), state.run_id, forged, capability=env.capability
            )
        assert env.runner.store.load(state.run_id) == state
        assert not env.port.calls and not env.lookup.calls


def test_reserved_turn_resume_does_not_dispatch_or_double_reserve(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start(), until={"INVESTIGATING"})
        env.cases.kernel.connection.execute(
            """CREATE TRIGGER cp4_fail_provider_intent BEFORE INSERT ON operation_intents
               WHEN NEW.intent_json LIKE '%graph.model.plan%'
               BEGIN SELECT RAISE(ABORT,'CP4 reservation window'); END"""
        )
        with pytest.raises(sqlite3.Error):
            env.advance(state)
        env.cases.kernel.connection.execute("DROP TRIGGER cp4_fail_provider_intent")
        reserved = env.runner.store.load(state.run_id)
        assert reserved.active_turn_input is not None
        env.restart()
        resumed = env.runner.resume(
            command_context(env.context.actor), state.run_id, capability=env.capability
        )
        assert resumed == reserved
        assert not env.port.calls and not env.lookup.calls
        final = env.drive(resumed)
        assert final.status == "AWAITING_REVIEW"
        assert final.budget.model_calls == len(env.port.calls) == 2
        assert final.budget.tool_calls == len(env.lookup.calls) == 1
        assert final.budget.reserved_tokens == 2 * env.spec.budgets.tokens_per_model_call
