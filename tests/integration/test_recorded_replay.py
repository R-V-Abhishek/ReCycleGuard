"""The loader reads a finished run's real audit stream; the scripted run is not model evidence."""

from recycleguard.config import Settings
from recycleguard.recorded_port import RecordedReplayModelPort, load_recordings
from tests.integration.test_a06_workflow import (
    approved_foundation as approved_foundation,
)
from tests.integration.test_a06_workflow import workflow as workflow
from tests.support.workflow import assess, plan


def test_recordings_match_the_run_and_replay_its_results(workflow):
    with workflow([plan(), assess()]) as env:
        state = env.drive(env.start())
        assert state.status == "AWAITING_REVIEW"
        recordings = load_recordings(env.cases.kernel, env.spec.run_id)
        assert [request for _, request, _ in env.port.calls] == [r for r, _ in recordings]
        port = RecordedReplayModelPort(Settings(mode="test", enable_test_adapters=True), recordings)
        for (context, request, _), (_, recorded) in zip(env.port.calls, recordings, strict=True):
            replayed = port.invoke(context, request)
            assert replayed.output.validated_output_or_null == (
                recorded.output.validated_output_or_null
            )
            assert replayed.output.exact_response_blob == recorded.output.exact_response_blob
            assert replayed.attempt_id == context.attempt_id
        assert port.remaining() == 0
