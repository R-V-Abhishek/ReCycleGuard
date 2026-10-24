"""Runtime roots and non-secret configuration."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class RuntimeRoots:
    data_root: Path
    benchmark_truth_root: Path | None = None

    @classmethod
    def from_environment(cls) -> "RuntimeRoots":
        data_root = Path(os.environ.get("RECYCLEGUARD_DATA_ROOT", ".recycleguard"))
        truth = os.environ.get("SEPARATE_BENCHMARK_TRUTH_ROOT")
        return cls(data_root, Path(truth) if truth else None)
