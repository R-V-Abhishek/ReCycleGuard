import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures/visible/a01"


@pytest.fixture
def context_payload():
    return json.loads((FIXTURES / "command_context.json").read_text())


@pytest.fixture
def quantity_payload():
    return json.loads((FIXTURES / "quantity.json").read_text())


@pytest.fixture(scope="session")
def rendered_pilot(tmp_path_factory):
    """Render the 48-case pilot once per session; consumers must treat it as read-only."""
    from benchmarks.generator.pilot_cases import build_pilot_cases
    from benchmarks.generator.render import render_case

    root = tmp_path_factory.mktemp("pilot-rendered")
    return [(case, render_case(case.world, root / case.split)) for case in build_pilot_cases()]
