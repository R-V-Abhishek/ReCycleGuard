"""C16 Runtime isolation and oracle access enforcement.

Pursuant to SYSTEM_DESIGN.md §11, CONTRACTS.md §10 (G11) and implementation plan.md §11:
- Restricts investigator access to visible mounts only.
- Denies and audits attempted access to hidden oracle, seeds, ground truth, and evaluator code.
- Sanitizes environment variables and validates mount points against symlink traversal.
"""

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from recycleguard.contracts.core import ID, BoundaryModel, Timestamp


class IsolationViolation(BoundaryModel):
    """Audit record for a forbidden access attempt by investigator runtime."""

    violation_id: ID
    attempted_path_or_target: str
    violation_kind: Literal[
        "FORBIDDEN_PATH",
        "ORACLE_ACCESS_ATTEMPT",
        "SYMLINK_TRAVERSAL",
        "FORBIDDEN_ENV_VAR",
        "EVALUATOR_CODE_MOUNT",
    ]
    recorded_at: Timestamp
    caller_actor_id: str | None = None
    action_taken: Literal["DENIED_AND_RECORDED"] = "DENIED_AND_RECORDED"


class IsolationReport(BoundaryModel):
    """Integrity report verifying runtime isolation constraints for a trial."""

    report_id: ID
    target_runtime_dir: str
    verified_at: Timestamp
    passed: bool
    violations: list[IsolationViolation]
    checked_rules_count: int


# Prohibited pattern regex for paths, filenames, and environment variables
FORBIDDEN_PATH_PATTERNS = [
    re.compile(r"(^|[\\/])benchmarks[\\/]evaluation($|[\\/])", re.IGNORECASE),
    re.compile(r"(^|[\\/])tests[\\/]fixtures[\\/]expected($|[\\/])", re.IGNORECASE),
    re.compile(r"(^|[\\/])\.git($|[\\/])", re.IGNORECASE),
    re.compile(r"(^|[\\/])\.env.*$", re.IGNORECASE),
    re.compile(r"(oracle|ground_truth|answer_key|secret_seeds)", re.IGNORECASE),
    re.compile(r"(^|[\\/])hidden($|[\\/])", re.IGNORECASE),
]

FORBIDDEN_ENV_PREFIXES = (
    "ORACLE_",
    "GROUND_TRUTH_",
    "BENCHMARK_SEED_",
    "EVAL_SECRET_",
    "HIDDEN_",
)


class OracleAccessDeniedError(PermissionError):
    """Raised when investigator code attempts to read or search hidden oracle data."""


class RuntimeIsolationEnforcer:
    """Enforces non-root, isolated execution sandbox and prevents oracle leakage."""

    def __init__(self, visible_root: Path | str, runtime_root: Path | str):
        self.visible_root = Path(visible_root).resolve()
        self.runtime_root = Path(runtime_root).resolve()
        self.violations: list[IsolationViolation] = []

    def check_path_access(
        self, target_path: Path | str, *, caller_actor_id: str | None = None
    ) -> Path:
        """Verify that a path is within permitted visible/runtime roots and not forbidden."""
        resolved = Path(target_path).resolve()
        target_str = str(resolved)

        # 1. Check against forbidden keywords / patterns
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(target_str):
                self._record_violation(
                    target_str,
                    "ORACLE_ACCESS_ATTEMPT" if "oracle" in target_str.lower() else "FORBIDDEN_PATH",
                    caller_actor_id,
                )
                raise OracleAccessDeniedError(
                    f"Access to path '{target_str}' denied by runtime isolation: "
                    "matched forbidden rule."
                )

        # 2. Check path containment (must be under visible_root or runtime_root)
        is_visible = False
        try:
            resolved.relative_to(self.visible_root)
            is_visible = True
        except ValueError:
            pass

        is_runtime = False
        try:
            resolved.relative_to(self.runtime_root)
            is_runtime = True
        except ValueError:
            pass

        if not (is_visible or is_runtime):
            self._record_violation(target_str, "FORBIDDEN_PATH", caller_actor_id)
            raise OracleAccessDeniedError(
                f"Path '{target_str}' is outside visible/runtime mounts: access blocked."
            )

        # 3. Check for symlink traversal attempting to break isolation
        if Path(target_path).is_symlink():
            real_target = Path(target_path).readlink().resolve()
            if not self._is_contained(real_target):
                self._record_violation(str(target_path), "SYMLINK_TRAVERSAL", caller_actor_id)
                raise OracleAccessDeniedError(
                    f"Symlink '{target_path}' resolves outside sandbox boundary."
                )

        return resolved

    def sanitize_environment(
        self, env: dict[str, str] | None = None, *, caller_actor_id: str | None = None
    ) -> dict[str, str]:
        """Strip answer-bearing environment variables, seeds, and secrets."""
        source = env if env is not None else dict(os.environ)
        sanitized = {}

        for k, v in source.items():
            if (
                any(k.upper().startswith(p) for p in FORBIDDEN_ENV_PREFIXES)
                or "ORACLE" in k.upper()
            ):
                self._record_violation(k, "FORBIDDEN_ENV_VAR", caller_actor_id)
            else:
                sanitized[k] = v

        return sanitized

    def validate_mounts(
        self, mount_points: list[Path | str], *, caller_actor_id: str | None = None
    ) -> IsolationReport:
        """Validate all provided mount directories to ensure no hidden code/data is mounted."""
        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        checked_rules = 0

        for mount in mount_points:
            checked_rules += 1
            m_path = Path(mount).resolve()
            for pattern in FORBIDDEN_PATH_PATTERNS:
                checked_rules += 1
                if pattern.search(str(m_path)):
                    self._record_violation(str(m_path), "EVALUATOR_CODE_MOUNT", caller_actor_id)

        passed = len(self.violations) == 0
        return IsolationReport(
            report_id=f"isoreport:{uuid4().hex[:20]}",
            target_runtime_dir=str(self.runtime_root),
            verified_at=now_iso,
            passed=passed,
            violations=list(self.violations),
            checked_rules_count=checked_rules,
        )

    def _is_contained(self, p: Path) -> bool:
        try:
            p.relative_to(self.visible_root)
            return True
        except ValueError:
            pass
        try:
            p.relative_to(self.runtime_root)
            return True
        except ValueError:
            pass
        return False

    def _record_violation(
        self, target: str, kind: str, caller_actor_id: str | None
    ) -> IsolationViolation:
        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        violation = IsolationViolation(
            violation_id=f"viol:{uuid4().hex[:16]}",
            attempted_path_or_target=target,
            violation_kind=kind,
            recorded_at=now_iso,
            caller_actor_id=caller_actor_id,
            action_taken="DENIED_AND_RECORDED",
        )
        self.violations.append(violation)
        return violation
