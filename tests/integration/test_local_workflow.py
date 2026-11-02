"""MODEL_BACKED composition gates only; these tests never emulate successful inference."""

import shutil

import pytest

from recycleguard.application import command_context, local_application
from recycleguard.config import Settings
from recycleguard.storage.authority import AuthorizationError, Capability
from recycleguard.workflow import WorkflowRunner, WorkflowStages
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a06_workflow import run_spec


class NoInference:
    def __init__(self):
        self.calls = 0

    def invoke(self, context, request):
        self.calls += 1
        raise AssertionError("gating tests must not invoke a model")


@pytest.fixture
def runtime(tmp_path, approved_foundation):
    root = tmp_path / "evidence"
    shutil.copytree(approved_foundation, root, ignore=shutil.ignore_patterns("reviewer.json"))
    with local_application(Settings(data_root=root)) as values:
        yield values, Settings(data_root=root), tmp_path / "cache.sqlite"


def make_runner(runtime, validator=None):
    (cases, _, _), settings, cache = runtime
    port = NoInference()

    def unavailable(context, spec):
        raise AssertionError("composition gate must not dispatch stages")

    return WorkflowRunner(
        cases,
        settings,
        model_port=port,
        tools={},
        stages=WorkflowStages(unavailable, unavailable, unavailable),
        checkpoint_path=cache,
        model_run_validator=validator,
    ), port


def test_model_backed_stays_unavailable_without_explicit_validator(runtime):
    (cases, context, capability), _, _ = runtime
    runner, port = make_runner(runtime)
    try:
        with pytest.raises(ValueError):
            runner.start_run(
                context, run_spec(cases, execution_kind="MODEL_BACKED"), capability=capability
            )
        assert port.calls == 0
    finally:
        runner.close()


def test_explicit_trusted_validator_checks_exact_pins_before_creating_run(runtime):
    (cases, context, capability), _, _ = runtime
    spec = run_spec(cases, execution_kind="MODEL_BACKED")
    validated = []

    def validate(candidate):
        if candidate.model != spec.model or candidate.prompt != spec.prompt:
            raise ValueError("model or prompt pin mismatch")
        validated.append(candidate)

    runner, port = make_runner(runtime, validate)
    try:
        state = runner.start_run(context, spec, capability=capability)
        assert state.status == "CREATED"
        assert validated == [spec]
        assert port.calls == 0
    finally:
        runner.close()


@pytest.mark.parametrize("field", ["model", "prompt"])
def test_model_or_prompt_pin_mismatch_prevents_run_creation(runtime, field):
    (cases, context, capability), _, _ = runtime
    spec = run_spec(cases, execution_kind="MODEL_BACKED")

    def validate(candidate):
        if candidate.model != spec.model or candidate.prompt != spec.prompt:
            raise ValueError("model or prompt pin mismatch")

    invalid = spec.model_copy(
        update={
            field: (spec.model if field == "model" else spec.prompt).model_copy(
                update={"digest": "f" * 64}
            )
        }
    )
    runner, port = make_runner(runtime, validate)
    try:
        with pytest.raises(ValueError, match="pin mismatch"):
            runner.start_run(context, invalid, capability=capability)
        with pytest.raises(ValueError):
            runner.store.load(spec.run_id)
        assert port.calls == 0
    finally:
        runner.close()


def test_trusted_model_validator_cannot_enable_scripted_execution_in_runtime(runtime):
    (cases, context, capability), _, _ = runtime
    validated = []
    runner, port = make_runner(runtime, validated.append)
    try:
        with pytest.raises(ValueError):
            runner.start_run(context, run_spec(cases), capability=capability)
        assert not validated and port.calls == 0
    finally:
        runner.close()


def test_unauthorized_caller_cannot_trigger_backend_validation(runtime):
    (cases, context, _), _, _ = runtime
    validated = []
    runner, port = make_runner(runtime, validated.append)
    try:
        with pytest.raises(AuthorizationError):
            runner.start_run(
                context, run_spec(cases, execution_kind="MODEL_BACKED"), capability=Capability()
            )
        assert not validated and port.calls == 0
    finally:
        runner.close()


def test_advance_revalidates_model_pins_before_any_state_or_external_dispatch(runtime):
    (cases, context, capability), _, _ = runtime
    spec = run_spec(cases, execution_kind="MODEL_BACKED")
    validated = []
    drifted = False

    def validate(candidate):
        validated.append(candidate)
        if drifted:
            raise ValueError("configured backend no longer matches frozen model/prompt pins")

    runner, port = make_runner(runtime, validate)
    try:
        state = runner.start_run(context, spec, capability=capability)
        drifted = True
        with pytest.raises(ValueError, match="frozen model/prompt pins"):
            runner.advance(
                command_context(context.actor), state.run_id, state.version, capability=capability
            )
        assert validated == [spec, spec]
        assert runner.store.load(state.run_id) == state
        assert runner.store.list_turns(state.run_id) == []
        assert port.calls == 0
    finally:
        runner.close()
