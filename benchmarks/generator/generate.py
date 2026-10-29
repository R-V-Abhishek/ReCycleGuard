"""Generator CLI: worlds -> visible dossiers (committed) + hidden record (gitignored).

    python -m benchmarks.generator.generate --visible-root tests/fixtures/visible \
        --hidden-root benchmarks/hidden [--check]

``--check`` regenerates the visible cases inside a scratch directory under the hidden root and
fails if any committed visible byte differs; it writes nothing to the visible root. S06 cases are
also validated: every recorded corruption must be visible in the rendered bytes.
"""

import argparse
import filecmp
import sys
import tempfile
from pathlib import Path

from benchmarks.generator.faults.validate import validate
from benchmarks.generator.hidden import write_hidden
from benchmarks.generator.render import render_case
from benchmarks.generator.s04_cases import build_s04_worlds
from benchmarks.generator.s05_cases import build_worlds
from benchmarks.generator.s06_cases import build_s06_cases


def _s06():
    return list(build_s06_cases())


# Each set has its own dataset version, and therefore its own hidden record directory. A set
# builder returns worlds, or S06 ``Corrupted`` cases that carry their clean counterpart.
WORLD_SETS = (build_worlds, build_s04_worlds, _s06)


def _world(item):
    return getattr(item, "world", item)


def _separate(visible: Path, hidden: Path):
    v, h = visible.resolve(), hidden.resolve()
    if v == h or v in h.parents or h in v.parents:
        raise SystemExit("hidden root must be outside the visible root (and vice versa)")


def _differences(expected: Path, actual: Path) -> list[str]:
    problems = []
    comparison = filecmp.dircmp(expected, actual)
    stack = [(comparison, "")]
    while stack:
        cmp, prefix = stack.pop()
        problems += [f"not committed {prefix}{n}" for n in cmp.left_only]
        problems += [f"unexpected committed {prefix}{n}" for n in cmp.right_only]
        for name in cmp.common_files:
            if (Path(cmp.left) / name).read_bytes() != (Path(cmp.right) / name).read_bytes():
                problems.append(f"changed {prefix}{name}")
        stack += [(sub, f"{prefix}{name}/") for name, sub in cmp.subdirs.items()]
    return problems


def _render(item, root: Path):
    out = render_case(_world(item), root)
    if item is not _world(item):
        problems = validate(item, out)
        if problems:
            raise SystemExit(f"{out.case_dir.name}: corruption not visible: {problems}")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--visible-root", type=Path, required=True)
    parser.add_argument("--hidden-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    _separate(args.visible_root, args.hidden_root)
    sets = [build() for build in WORLD_SETS]

    if args.check:
        args.hidden_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=args.hidden_root, prefix=".check_") as scratch:
            problems = []
            for item in (item for group in sets for item in group):
                out = _render(item, Path(scratch))
                committed = args.visible_root / out.case_dir.name
                if not committed.is_dir():
                    problems.append(f"missing case directory {committed}")
                    continue
                problems += [
                    f"{committed.name}: {p}" for p in _differences(out.case_dir, committed)
                ]
        for problem in problems:
            print(problem, file=sys.stderr)
        print("visible cases are current" if not problems else f"{len(problems)} differences")
        return 1 if problems else 0

    for group in sets:
        rendered = [_render(item, args.visible_root) for item in group]
        worlds = [_world(item) for item in group]
        cases = group if group and group[0] is not worlds[0] else None
        root = write_hidden(args.hidden_root, worlds, rendered, cases=cases)
        for out in rendered:
            print(f"visible: {out.case_dir}")
        print(f"hidden:  {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
