"""Generator CLI: worlds -> visible dossiers (committed) + hidden record (gitignored).

    python -m benchmarks.generator.generate --visible-root tests/fixtures/visible \
        --hidden-root benchmarks/hidden [--check]

``--check`` regenerates the visible cases inside a scratch directory under the hidden root and
fails if any committed visible byte differs; it writes nothing to the visible root. S06 cases are
also validated: every recorded corruption must be visible in the rendered bytes.

The S07 pilot renders its development split beside the other visible cases and its held-out split
under ``--heldout-root`` (default ``benchmarks/heldout/visible``, gitignored); ``--check`` compares
the held-out split with the committed digest seal instead of committed files.
"""

import argparse
import filecmp
import json
import sys
import tempfile
from pathlib import Path

from benchmarks.evaluation.oracle import write_oracle_records
from benchmarks.generator import pilot
from benchmarks.generator.faults.validate import validate
from benchmarks.generator.hidden import write_hidden
from benchmarks.generator.pilot_cases import DEV, SPLIT_POLICY, build_pilot_cases
from benchmarks.generator.render import render_case
from benchmarks.generator.s04_cases import build_s04_worlds
from benchmarks.generator.s05_cases import build_worlds
from benchmarks.generator.s06_cases import build_s06_cases

# Sealed held-out visible dossiers: outside version control (see .gitignore and pilot.py).
HELDOUT_ROOT = Path(__file__).resolve().parents[1] / "heldout" / "visible"


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


def _pilot(args, scratch: Path | None) -> list[str]:
    """Render the S07 pilot: development cases beside the other visible cases, held-out cases
    under the held-out root, then check split independence, leakage and the seal.

    With ``scratch`` (``--check``) everything renders there, development bytes are compared with
    the committed fixtures and held-out digests with the committed seal; nothing is written."""
    cases = list(build_pilot_cases())
    problems = pilot.split_problems(cases)
    rendered = []
    for case in cases:
        if scratch is not None:
            root = scratch / "pilot" / case.split
        else:
            root = args.visible_root if case.split == DEV else args.heldout_root
        rendered.append(_render(case.corrupted, root))
    problems += pilot.leakage_problems(cases, rendered)
    sealed = pilot.seal(cases, rendered)
    if scratch is not None:
        for case, out in zip(cases, rendered, strict=True):
            if case.split != DEV:
                continue
            committed = args.visible_root / out.case_dir.name
            if not committed.is_dir():
                problems.append(f"missing case directory {committed}")
                continue
            problems += [f"{committed.name}: {p}" for p in _differences(out.case_dir, committed)]
        expected = (
            json.loads(pilot.SEAL_PATH.read_text("utf-8")) if pilot.SEAL_PATH.exists() else {}
        )
        problems += pilot.seal_problems(expected, sealed)
        return problems
    if problems:
        return problems
    worlds = [case.world for case in cases]
    splits = {
        case.world.case_id: {
            "split": case.split,
            "template": case.spec.template_key,
            "timeline_group": case.world.timeline_group,
            "producer": case.world.producer.legal_name,
            "combination": "+".join(case.spec.combination),
        }
        for case in cases
    }
    root = write_hidden(
        args.hidden_root,
        worlds,
        rendered,
        cases=[case.corrupted for case in cases],
        split_policy=SPLIT_POLICY,
        splits=splits,
    )
    write_oracle_records(args.hidden_root, worlds, rendered)
    pilot.SEAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    pilot.SEAL_PATH.write_bytes(pilot.seal_bytes(sealed))
    for case, out in zip(cases, rendered, strict=True):
        print(f"{'visible' if case.split == DEV else 'sealed'}: {out.case_dir}")
    print(f"hidden:  {root}")
    print(f"seal:    {pilot.SEAL_PATH}")
    return []


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--visible-root", type=Path, required=True)
    parser.add_argument("--hidden-root", type=Path, required=True)
    parser.add_argument("--heldout-root", type=Path, default=HELDOUT_ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    _separate(args.visible_root, args.hidden_root)
    _separate(args.visible_root, args.heldout_root)
    _separate(args.hidden_root, args.heldout_root)
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
            problems += _pilot(args, Path(scratch))
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
    problems = _pilot(args, None)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"pilot not written: {len(problems)} problems")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
