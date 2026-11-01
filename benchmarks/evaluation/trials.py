"""C16 trial coordinator: schedule, append-only ledger, kill switch, caps and safe resume.

Evaluator-only. The coordinator never calls a model itself: a caller supplies a
``runner`` that executes one scheduled trial (for example through the CLI in a fresh
data root). It records every attempt, including failures, and stops at run boundaries.
"""

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

TERMINAL = {"SUCCESS", "FAILED", "NOT_RUN"}
Status = Literal["STARTED", "SUCCESS", "FAILED", "INFRA_FAILED", "INTERRUPTED", "NOT_RUN"]


class TrialSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    trial_id: str
    case_id: str
    variant: str
    repeat: int
    position: int


class TrialOutcome(BaseModel):
    """What a runner reports. ``tokens`` stays None when the provider did not report it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["SUCCESS", "FAILED", "INFRA_FAILED"]
    tokens: int | None = None
    detail: str = ""
    result_digest: str | None = None


def build_schedule(
    case_ids: Iterable[str], variants: tuple[str, str], repeats: int
) -> list[TrialSpec]:
    """Repeat-major order; the two variants alternate which runs first from case to case."""
    cases = list(case_ids)
    if len(set(cases)) != len(cases):
        raise ValueError("case ids must be unique")
    if len(variants) != 2 or len(set(variants)) != 2 or repeats < 1:
        raise ValueError("two distinct variants and at least one repeat are required")
    schedule = []
    for repeat in range(1, repeats + 1):
        for index, case in enumerate(cases):
            ordered = variants if (index + repeat) % 2 == 0 else variants[::-1]
            for variant in ordered:
                schedule.append(
                    TrialSpec(
                        trial_id=f"{case}|{variant}|r{repeat}",
                        case_id=case,
                        variant=variant,
                        repeat=repeat,
                        position=len(schedule),
                    )
                )
    return schedule


class Ledger:
    """Append-only JSONL. Rows are never edited; each write is fsynced."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def rows(self) -> list[dict]:
        return [json.loads(line) for line in self.path.read_text("utf-8").splitlines() if line]

    def append(self, row: dict) -> None:
        row = {**row, "at": datetime.now(UTC).isoformat()}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def terminal(self) -> set[str]:
        return {r["trial_id"] for r in self.rows() if r["status"] in TERMINAL}

    def attempts(self, trial_id: str) -> int:
        return sum(1 for r in self.rows() if r["trial_id"] == trial_id and r["status"] == "STARTED")


def verify_seals(output: Path) -> int:
    """Every recorded digest must match its stored result. Returns the number checked."""
    checked = 0
    for row in Ledger(output / "ledger.jsonl").rows():
        digest = row.get("result_digest")
        if digest is None:
            continue
        stored = output / "results" / f"{digest}.json"
        if not stored.is_file():
            raise ValueError(f"sealed result is missing: {row['trial_id']}")
        if hashlib.sha256(stored.read_bytes()).hexdigest() != digest:
            raise ValueError(f"sealed result changed: {row['trial_id']}")
        checked += 1
    return checked


@dataclass(frozen=True)
class Caps:
    wall_seconds: float = 7 * 3600
    tokens: int = 2_000_000
    consecutive_infra_failures: int = 3
    max_attempts: int = 2


@dataclass
class RunSummary:
    stopped_because: str | None
    completed: int
    wall_seconds: float
    tokens: int


class Coordinator:
    def __init__(
        self,
        schedule: list[TrialSpec],
        ledger: Ledger,
        runner: Callable[[TrialSpec], TrialOutcome],
        kill_switch: Path,
        caps: Caps | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.schedule, self.ledger, self.runner = schedule, ledger, runner
        self.kill_switch, self.caps, self.clock = kill_switch, caps or Caps(), clock

    def _recover(self) -> None:
        """A STARTED row without a later result means the process died mid-trial."""
        open_trials: dict[str, int] = {}
        for row in self.ledger.rows():
            if row["status"] == "STARTED":
                open_trials[row["trial_id"]] = open_trials.get(row["trial_id"], 0) + 1
            elif row["trial_id"] in open_trials:
                open_trials[row["trial_id"]] -= 1
        for trial_id, count in open_trials.items():
            if count > 0:
                self.ledger.append(
                    {"trial_id": trial_id, "status": "INTERRUPTED", "detail": "no result recorded"}
                )

    def run(self) -> RunSummary:
        self._recover()
        started, tokens, completed, infra_streak = self.clock(), 0, 0, 0
        reason = None
        for spec in self.schedule:
            if spec.trial_id in self.ledger.terminal():
                continue
            if self.kill_switch.exists():
                reason = "KILL_SWITCH"
            elif self.clock() - started >= self.caps.wall_seconds:
                reason = "WALL_CAP"
            elif tokens >= self.caps.tokens:
                reason = "TOKEN_CAP"
            elif infra_streak >= self.caps.consecutive_infra_failures:
                reason = "INFRASTRUCTURE_FAILURES"
            if reason:
                break
            attempt = self.ledger.attempts(spec.trial_id) + 1
            if attempt > self.caps.max_attempts:
                self.ledger.append(
                    {
                        "trial_id": spec.trial_id,
                        "status": "FAILED",
                        "detail": "attempts exhausted after infrastructure failures",
                    }
                )
                continue
            self.ledger.append({"trial_id": spec.trial_id, "status": "STARTED", "attempt": attempt})
            began = self.clock()
            try:
                outcome = self.runner(spec)
            except Exception as exc:  # a runner crash is an infrastructure failure, kept
                outcome = TrialOutcome(status="INFRA_FAILED", detail=f"{type(exc).__name__}: {exc}")
            tokens += outcome.tokens or 0
            infra_streak = infra_streak + 1 if outcome.status == "INFRA_FAILED" else 0
            self.ledger.append(
                {
                    "trial_id": spec.trial_id,
                    "status": outcome.status,
                    "attempt": attempt,
                    "wall_seconds": round(self.clock() - began, 3),
                    "tokens": outcome.tokens,
                    "detail": outcome.detail,
                    "result_digest": outcome.result_digest,
                }
            )
            completed += 1
        return RunSummary(reason, completed, self.clock() - started, tokens)

    def close_unfinished(self, reason: str) -> int:
        """At a deadline, mark every non-terminal row NOT_RUN. Rows are counted, never dropped."""
        done = self.ledger.terminal()
        count = 0
        for spec in self.schedule:
            if spec.trial_id not in done:
                self.ledger.append(
                    {"trial_id": spec.trial_id, "status": "NOT_RUN", "detail": reason}
                )
                count += 1
        return count
