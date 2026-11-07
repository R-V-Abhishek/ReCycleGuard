"""Write the MG2 prompt files from the registry in src/recycleguard/agents/registry.py.

The registry is the source; a prompt file is its output. A unit test fails when a committed file
differs from what the registry produces, so edit the registry and rerun this, never the JSON.

    uv run scripts/write_mg2_prompts.py          # write every registered version
    uv run scripts/write_mg2_prompts.py --check  # exit 1 when a file is missing or differs
"""

import json
import sys
from pathlib import Path

from recycleguard.agents.registry import VERSIONS, prompt_document

FOLDER = Path(__file__).resolve().parents[1] / "docs/checkpoints/mg2/prompts"


def main(argv):
    check = argv == ["--check"]
    if argv and not check:
        raise SystemExit(__doc__)
    stale = []
    for version in VERSIONS:
        path = FOLDER / f"{version}.json"
        text = json.dumps(prompt_document(version), indent=2) + "\n"
        if check:
            if not path.is_file() or json.loads(path.read_text("utf-8")) != json.loads(text):
                stale.append(version)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, "utf-8")
            print(f"wrote {path.name}")
    if stale:
        raise SystemExit(f"out of date: {stale}; run scripts/write_mg2_prompts.py")


if __name__ == "__main__":
    main(sys.argv[1:])
