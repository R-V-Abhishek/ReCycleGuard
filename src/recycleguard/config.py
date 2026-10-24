"""Explicit runtime roots. Hidden truth is never part of runtime configuration."""

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    data_root: Path = Path(".recycleguard")
    intake_root: Path = Path(".recycleguard/intake")
    output_root: Path = Path(".recycleguard/output")
    mode: Literal["runtime", "test", "evaluation"] = "runtime"
    enable_test_adapters: bool = False

    @model_validator(mode="after")
    def test_only(self):
        if self.enable_test_adapters and self.mode != "test":
            raise ValueError("test adapters are allowed only in test mode")
        return self

    @classmethod
    def from_environment(cls):
        values = {}
        for field in ("data_root", "intake_root", "output_root", "mode", "enable_test_adapters"):
            key = f"RECYCLEGUARD_{field.upper()}"
            if key in os.environ:
                values[field] = os.environ[key]
        return cls.model_validate(values)
