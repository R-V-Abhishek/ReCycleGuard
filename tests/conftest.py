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
