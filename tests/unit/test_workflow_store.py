"""Real SQLite graph ledger: authorization, exact replay, CAS and atomic recovery."""

import sqlite3

import pytest

from recycleguard.application import command_context
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import ActorRef
from recycleguard.contracts.workflow import (
    BudgetLimits,
    BudgetUsage,
    ConfigurationPin,
    RunSpec,
    RunState,
    StageOutcome,
    TurnManifest,
)
from recycleguard.storage import AuditKernel, BlobStore, canonical_json_bytes
from recycleguard.storage.authority import (
    AuthorizationError,
    Capability,
    LocalAuthority,
    TrustedPrincipal,
)
from recycleguard.storage.blob_store import BlobIntegrityError
from recycleguard.workflow.store import GraphStore

NOW = "2026-10-28T00:00:00Z"
ACTOR = ActorRef(
    actor_id="service:graph_test", actor_kind="SERVICE", authenticated_session_ref=None
)


def spec(run_id="run:test"):
    pin = ConfigurationPin(configuration_id="config:test", digest="0" * 64)
    return RunSpec(
        run_id=run_id,
        case_snapshot={"snapshot_id": "snapshot:case", "membership_digest": "1" * 64},
        corpus_snapshot={"snapshot_id": "snapshot:corpus", "membership_digest": "2" * 64},
        profile={"profile_id": "profile:test", "profile_version": "test", "digest": "3" * 64},
        index=pin,
        code_revision="test-revision",
        dependency_lock_digest="4" * 64,
        adapters=pin,
        tools=pin,
        prompt=pin,
        model=pin,
        retrieval_policy=pin,
        audit_policy=pin,
        security_policy=pin,
        experiment_variant="scripted-test",
        finding_ids=["finding:one"],
        budgets=BudgetLimits(),
    )


def context(run_id="run:test", actor=ACTOR):
    return command_context(actor).model_copy(
        update={"run_id": run_id, "case_version_id": "snapshot:case"}
    )


@pytest.fixture
def environment(tmp_path):
    authority = LocalAuthority({"service": TrustedPrincipal(ACTOR, frozenset({"graph."}))})
    cap = authority.issue("service")
    blobs = BlobStore(tmp_path / "blobs")
    kernel = AuditKernel(tmp_path / "state.sqlite", blobs, authority=authority)
    store = GraphStore(kernel)
    yield store, cap, authority
    kernel.close()


def start(store, cap):
    return store.start(context(), spec(), capability=cap, now=NOW)


def outcome():
    return StageOutcome(
        disposition="QUALIFIED",
        evidence_refs=[],
        output_blob=None,
        concise_decision="Synthetic fixture requires human review.",
    )


def manifest(store, state, *, status="COMPLETED"):
    coverage = store.blobs.put(canonical_json_bytes({"coverage": "QUALIFIED"}), "application/json")
    return TurnManifest(
        turn_id="turn:one",
        run_id=state.run_id,
        turn_index=1,
        previous_turn_id=None,
        input_state_blob=state.active_turn_input or store.state_blob(state.run_id),
        output_state_blob=None,
        pinned_membership_refs=["snapshot:case", "snapshot:corpus"],
        operation_ids_in_order=[],
        context_manifest_ids=[],
        retrieval_attempt_ids=[],
        calculation_ids=[],
        finding_revision_ids=[],
        plan_refs=[],
        observation_assessment_refs=[],
        plan_revised=False,
        coverage_summary_blob=coverage,
        budget_before=BudgetUsage(),
        budget_after=state.budget,
        turn_status=status,
        concise_decision="Synthetic turn only.",
        stop_reason=None,
        first_event_sequence=0,
        last_event_sequence=0,
    )


def test_start_pins_spec_and_replays_exactly_without_duplicate_runs(environment):
    store, cap, _ = environment
    ctx = context()
    state = store.start(ctx, spec(), capability=cap, now=NOW)
    assert state.version == 1 and state.current_turn == 0 and state.status == "CREATED"
    assert state.last_audit_sequence == 1
    assert store.spec(state.run_id) == spec()
    assert store.load(state.run_id) == state
    assert store.start(ctx, spec(), capability=cap, now=NOW) == state
    assert store.start(ctx, spec(), capability=cap, now="2026-10-28T00:01:00Z") == state
    assert len(store.kernel.list_attempts(ctx.operation_id)) == 1
    assert len(store.kernel.list_stream_events("stream:run:test")) == 1
    with pytest.raises(ValueError, match="already exists"):
        store.start(context(), spec(), capability=cap, now=NOW)
    with pytest.raises(ValueError, match="different intent|different input"):
        store.start(
            ctx,
            spec().model_copy(update={"experiment_variant": "changed"}),
            capability=cap,
            now=NOW,
        )


def test_graph_writes_require_service_capability_and_exact_run_pin(environment):
    store, cap, _ = environment
    with pytest.raises(AuthorizationError):
        store.start(context(), spec(), capability=Capability(), now=NOW)
    with pytest.raises(ValueError, match="exact run"):
        store.start(context("run:other"), spec(), capability=cap, now=NOW)
    assert list(store.blobs.objects.glob("*/*")) == []


def test_model_graph_grant_cannot_write_authoritative_state(tmp_path):
    actor = ActorRef(
        actor_id="model:proposal", actor_kind="MODEL_PROPOSAL", authenticated_session_ref=None
    )
    authority = LocalAuthority({"model": TrustedPrincipal(actor, frozenset({"graph."}))})
    kernel = AuditKernel(tmp_path / "state.sqlite", BlobStore(tmp_path), authority=authority)
    try:
        store = GraphStore(kernel)
        with pytest.raises(AuthorizationError, match="SERVICE"):
            store.start(context(actor=actor), spec(), capability=authority.issue("model"), now=NOW)
    finally:
        kernel.close()


def test_state_cas_and_last_sequence_include_intervening_archives(environment):
    store, cap, _ = environment
    initial = start(store, cap)
    blob = store.state_blob(initial.run_id)
    record_context = context()
    stored = store.archive(record_context, "graph.preflight", outcome(), capability=cap)
    assert store.read(record_context.operation_id, StageOutcome) == outcome()
    assert store.archive(record_context, "graph.preflight", outcome(), capability=cap) == stored
    ctx = context()
    changed = initial.model_copy(update={"status": "PREFLIGHT"})
    updated = store.save(ctx, changed, 1, capability=cap)
    assert updated.version == 2 and updated.last_audit_sequence == 3
    assert store.save(ctx, changed, 1, capability=cap) == updated
    assert RunState.model_validate_json(store.blobs.get(blob)) == initial
    with pytest.raises(ValueError, match="stale graph state"):
        store.save(context(), initial, 1, capability=cap)
    with pytest.raises(ValueError, match="different intent|different input"):
        store.archive(
            record_context,
            "graph.preflight",
            outcome().model_copy(update={"concise_decision": "Different request."}),
            capability=cap,
        )


def test_result_audit_failure_rolls_back_state_and_can_resume(environment):
    store, cap, _ = environment
    initial = start(store, cap)
    changed = initial.model_copy(update={"status": "PREFLIGHT"})
    ctx = context()
    store.connection.execute("""CREATE TRIGGER fail_graph BEFORE INSERT ON audit_events
      WHEN NEW.event_json LIKE '%graph.state.result%'
      BEGIN SELECT RAISE(ABORT,'simulated graph audit failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="simulated"):
        store.save(ctx, changed, 1, capability=cap)
    assert store.load(initial.run_id) == initial
    assert store.kernel.get_result(ctx.operation_id) is None
    store.connection.execute("DROP TRIGGER fail_graph")
    resumed = store.save(ctx, changed, 1, capability=cap)
    assert resumed.version == 2 and resumed.last_audit_sequence == 2


def test_state_survives_reopen_and_second_connection_cas(environment, tmp_path):
    store, cap, authority = environment
    initial = start(store, cap)
    kernel = AuditKernel(tmp_path / "state.sqlite", store.blobs, authority=authority)
    try:
        other = GraphStore(kernel)
        assert other.load(initial.run_id) == initial
        updated = other.save(
            context(), initial.model_copy(update={"status": "PREFLIGHT"}), 1, capability=cap
        )
        with pytest.raises(ValueError, match="stale graph state"):
            store.save(context(), initial, 1, capability=cap)
        assert store.load(initial.run_id) == updated
    finally:
        kernel.close()


@pytest.mark.parametrize("turn_status", ["COMPLETED", "FAILED", "CANCELLED"])
def test_turn_commit_pins_exact_states_and_preserves_caller_status(environment, turn_status):
    store, cap, _ = environment
    initial = start(store, cap)
    input_ref = store.state_blob(initial.run_id)
    reserved = store.save(
        context(),
        initial.model_copy(
            update={
                "active_turn_input": input_ref,
                "pending_operation_id": "operation:pending",
                "pending_attempt_id": "attempt:pending",
            }
        ),
        1,
        capability=cap,
    )
    turn = manifest(store, reserved, status=turn_status)
    ctx = context()
    final = store.finish_turn(ctx, reserved, 2, turn, capability=cap)
    assert final.current_turn == 1 and final.version == 3
    assert final.pending_operation_id is None and final.active_turn_input is None
    assert final.pending_attempt_id is None
    assert store.finish_turn(ctx, reserved, 2, turn, capability=cap) == final
    saved = store.last_turn(initial.run_id)
    assert store.list_turns(initial.run_id) == [saved]
    assert saved.turn_status == turn_status
    assert saved.input_state_blob == input_ref
    assert saved.output_state_blob == store.state_blob(initial.run_id)
    assert (saved.first_event_sequence, saved.last_event_sequence) == (2, 3)
    assert final.last_audit_sequence == saved.last_event_sequence


def test_turn_manifest_and_state_are_atomic_with_audit(environment):
    store, cap, _ = environment
    initial = start(store, cap)
    turn = manifest(store, initial)
    ctx = context()
    store.connection.execute("""CREATE TRIGGER fail_turn BEFORE INSERT ON audit_events
      WHEN NEW.event_json LIKE '%graph.turn.result%'
      BEGIN SELECT RAISE(ABORT,'simulated turn audit failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.finish_turn(ctx, initial, 1, turn, capability=cap)
    assert store.load(initial.run_id) == initial
    assert store.list_turns(initial.run_id) == []
    assert store.kernel.get_result(ctx.operation_id) is None
    store.connection.execute("DROP TRIGGER fail_turn")
    final = store.finish_turn(ctx, initial, 1, turn, capability=cap)
    assert final.current_turn == 1 and store.last_turn(initial.run_id) is not None


@pytest.mark.parametrize(
    "status", ["COMPLETED", "CANCELLED", "FAILED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"]
)
def test_terminal_state_rejects_further_mutations(environment, status):
    store, cap, _ = environment
    initial = start(store, cap)
    terminal = store.save(
        context(), initial.model_copy(update={"status": status}), 1, capability=cap
    )
    with pytest.raises(ValueError, match="terminal"):
        store.save(context(), terminal.model_copy(update={"status": "CREATED"}), 2, capability=cap)
    with pytest.raises(ValueError, match="terminal"):
        store.archive(context(), "graph.check", outcome(), capability=cap)


def test_tampered_audit_event_is_rejected_on_read(environment):
    store, cap, _ = environment
    state = start(store, cap)
    event = store.kernel.list_stream_events(f"stream:{state.run_id}")[0]
    corrupted = event.model_copy(update={"event_hash": "0" * 64})
    store.connection.execute(
        "UPDATE audit_events SET event_json=? WHERE event_id=?",
        (corrupted.model_dump_json(), event.event_id),
    )
    store.connection.commit()
    with pytest.raises(ValueError, match="hash chain"):
        store.load(state.run_id)


def test_case_snapshot_pin_is_checked_before_archiving(environment):
    store, cap, _ = environment
    bad = context().model_copy(update={"case_version_id": "snapshot:other"})
    with pytest.raises(ValueError, match="exact case snapshot"):
        store.start(bad, spec(), capability=cap, now=NOW)
    initial = start(store, cap)
    with pytest.raises(ValueError, match="exact case snapshot"):
        store.save(bad, initial, 1, capability=cap)


def test_archived_blob_tampering_is_detected_before_replay(environment):
    store, cap, _ = environment
    start(store, cap)
    ctx = context()
    ref = store.archive(ctx, "graph.preflight", outcome(), capability=cap)
    path = store.blobs.objects / ref.sha256[:2] / ref.sha256
    path.write_bytes(b"X" * ref.byte_length)
    with pytest.raises(BlobIntegrityError):
        store.read(ctx.operation_id, StageOutcome)


def test_active_turn_input_cannot_be_borrowed_from_another_run(environment):
    store, cap, _ = environment
    state = start(store, cap)
    other = spec("run:other")
    store.start(context("run:other"), other, capability=cap, now=NOW)
    contaminated = state.model_copy(update={"active_turn_input": store.state_blob("run:other")})
    with pytest.raises(ValueError, match="different run or turn"):
        store.save(context(), contaminated, 1, capability=cap)


def test_terminal_retry_is_bound_to_actual_registered_attempt(environment):
    store, cap, _ = environment
    start(store, cap)
    ctx = context()
    request = store.blobs.put(canonical_json_bytes({"request": "same"}), "application/json")
    first = OperationIntent(
        context=ctx,
        idempotency_key=ctx.idempotency_key,
        event_type="graph.tool.test",
        payload=request,
        stream_id="stream:run:test",
    )
    store.kernel.commit_intent(first, capability=cap)
    store.kernel.commit_result(
        first,
        OperationResult(
            operation_id=ctx.operation_id,
            attempt_id=ctx.attempt_id,
            status="FAILED",
            payload=request,
            issue_codes=["PROVIDER_INVALID_OUTPUT"],
        ),
        capability=cap,
        terminal=False,
    )
    assert store.read(ctx.operation_id, StageOutcome) is None
    retry_context = ctx.model_copy(update={"attempt_id": f"attempt:retry_{ctx.idempotency_key}"})
    retry = first.model_copy(update={"context": retry_context})
    store.kernel.commit_intent(retry, capability=cap)
    output = store.blobs.put(
        canonical_json_bytes(outcome().model_dump(mode="json")), "application/json"
    )
    store.kernel.commit_result(
        retry,
        OperationResult(
            operation_id=ctx.operation_id,
            attempt_id=retry_context.attempt_id,
            status="SUCCESS",
            payload=output,
        ),
        capability=cap,
    )
    assert store.kernel.get_intent(ctx.operation_id).context.attempt_id == ctx.attempt_id
    assert store.read(ctx.operation_id, StageOutcome) == outcome()
    assert len(store.kernel.list_attempts(ctx.operation_id)) == 2


def test_spec_pointer_cannot_substitute_a_valid_same_run_blob(environment):
    store, cap, _ = environment
    state = start(store, cap)
    changed = spec().model_copy(update={"experiment_variant": "unaudited-change"})
    ref = store.blobs.put(canonical_json_bytes(changed.model_dump(mode="json")), "application/json")
    store.connection.execute(
        "UPDATE workflow_runs SET spec_blob=? WHERE run_id=?", (ref.model_dump_json(), state.run_id)
    )
    store.connection.commit()
    with pytest.raises(ValueError, match="audited start"):
        store.spec(state.run_id)


def test_turn_pointer_cannot_substitute_a_valid_same_run_manifest_blob(environment):
    store, cap, _ = environment
    state = start(store, cap)
    store.finish_turn(context(), state, 1, manifest(store, state), capability=cap)
    original = store.last_turn(state.run_id)
    changed = original.model_copy(update={"concise_decision": "unaudited-change"})
    ref = store.blobs.put(canonical_json_bytes(changed.model_dump(mode="json")), "application/json")
    store.connection.execute(
        "UPDATE workflow_turns SET manifest_blob=? WHERE turn_id=?",
        (ref.model_dump_json(), original.turn_id),
    )
    store.connection.commit()
    with pytest.raises(ValueError, match="audited turn result"):
        store.list_turns(state.run_id)
