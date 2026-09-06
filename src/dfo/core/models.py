from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from dfo.core.exceptions import (
    InterpolationCycleError,
    InterpolationError,
    InterpolationSyntaxError,
    InterpolationTypeError,
    UnknownReferenceError,
)

EXACT_PLACEHOLDER_RE = re.compile(r"^\$\{([^}]+)\}$")

# Finds placeholders embedded anywhere in a string:
#     "${env.ROOT}/rtl/${gen.params.top}.v"
PLACEHOLDER_RE = re.compile(r"\$\{([^{}]+)\}")
STRAY_PLACEHOLDER_FRAGMENTS_RE = re.compile(r"(?:\$\{|\})")

# from dfo.core.exceptions import CycleError, ValidationError


class StepStatus(StrEnum):
    """Execution status of an individual step or flow."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class Environment(BaseModel):
    """Environment variables for the flow executions model."""

    model_config = {"extra": "allow"}


class Artifact(BaseModel):
    """"""

    path: str
    checksum: str | None = None

    def compute_checksum(self, base_dir: Path) -> str:
        full_path = base_dir / self.path
        if not full_path.exists() or not full_path.is_file():
            return ""
        sha256 = hashlib.sha256()
        sha256.update(full_path.read_bytes())
        return sha256.hexdigest()[:16]


class Step(BaseModel):
    """"""

    id: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    timeout: int | None = Field(default=None, ge=1)

    @field_validator("artifacts", mode="before")
    @classmethod
    def normalize_artifacts(cls, v: list[str] | None) -> list[str]:
        if v is None:
            return []
        return v


class Flow(BaseModel):
    name: str
    version: str = "1.0.0"
    environment: Environment = Field(default_factory=Environment)
    steps: list[Step]

    @field_validator("steps", mode="after")
    @classmethod
    def check_unique_ids(cls, steps: list[Step]) -> list[Step]:
        """Ensure unique step IDs."""
        ids = [step.id for step in steps]
        if len(ids) != len(set(ids)):
            from collections import Counter

            duplicates = [id for id, count in Counter(ids).items() if count > 1]
            raise ValueError(f"Duplicate ids in steps: {duplicates}")
        return steps

    @field_validator("steps", mode="after")
    @classmethod
    def ensure_existing_steps(cls, steps: list[Step]) -> list[Step]:
        step_ids = [s.id for s in steps]

        for step in steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(f"Step {step.id} depends on an unknown step.")
        return steps

    @model_validator(mode="after")
    def check_no_cycles(self) -> Self:
        """Check for no cycles in the dependencies of steps."""
        # build adjacency list
        graph: dict[str, list[str]] = {s.id: s.depends_on for s in self.steps}

        visited: set[str] = set()
        recursion_stack: set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            recursion_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in recursion_stack:
                    return True
            recursion_stack.remove(node)
            return False

        for step_id in graph:
            if step_id not in visited and has_cycle(step_id):
                from dfo.core.exceptions import CycleError

                raise CycleError("Dependency cycle detected in flow steps.")
        return self

    def get_step(self, step_id: str) -> Step:
        """Get step by its id."""
        for step in self.steps:
            if step.id == step_id:
                return step
        raise ValueError(f"Step '{step_id}' not found")

    @classmethod
    def from_yaml(cls, path: Path) -> Flow:
        """Load Flow from a YAML file."""
        import yaml

        raw = yaml.safe_load(path.read_text())
        return cls.model_validate(raw)

    def interpolate(self) -> Flow:
        """Interpolate references"""
        working = self.model_dump()

        context: dict[str, object] = {"env": working["environment"]}
        for step in working["steps"]:
            context[step["id"]] = {"params": step["params"]}
        # Matches a COMPLETE placeholder such as:
        #     ${env.ROOT}
        #     ${gen.params.output_dir}

        def lookup_path(path: str) -> object:
            path_segments = path.split(".")
            current_context: object = context
            for path_seg in path_segments:
                if not isinstance(current_context, dict):
                    raise UnknownReferenceError(
                        "Cannot descend into element which is not a dict"
                    )

                if path_seg not in current_context:
                    raise UnknownReferenceError(
                        "Could not find the key for the reference in the context."
                    )

                current_context = current_context[path_seg]

            return current_context

        def resolve_reference(path: str, stack: tuple[str, ...]) -> object:
            if path in stack:
                raise InterpolationCycleError(
                    "Detected a cycle during value interpolation."
                )
            raw_value = lookup_path(path)
            new_stack = (*stack, path)
            return resolve_value(raw_value, new_stack)

        def resolve_string(text: str, stack: tuple[str, ...]) -> object:
            # check for invalid interpolation strings
            # removed_correct_placeholders = PLACEHOLDER_RE.sub("", text)
            removed_correct_placeholders = PLACEHOLDER_RE.sub("", text)
            stray_fragments = STRAY_PLACEHOLDER_FRAGMENTS_RE.findall(
                removed_correct_placeholders
            )
            if len(stray_fragments) > 0:
                raise InterpolationSyntaxError("Stray interpolation fragments found.")

            match = EXACT_PLACEHOLDER_RE.fullmatch(text)

            # exact placeholder
            if match:
                return resolve_reference(match.group(1), stack)

            # placeholder embedded in a larger text
            def replacer(match: re.Match[str]) -> str:
                path = match.group(1)
                value = resolve_reference(path, stack)

                if isinstance(value, (dict, list)):
                    raise InterpolationTypeError(
                        f"Attempted to interpolate a {type(value)} into a str."
                    )

                return str(value)

            return PLACEHOLDER_RE.sub(replacer, text)

        def resolve_value(value: object, stack: tuple[str, ...]) -> object:
            if isinstance(value, dict):
                return {
                    key: resolve_value(value, stack) for key, value in value.items()
                }
            if isinstance(value, list):
                return [resolve_value(item, stack) for item in value]
            if isinstance(value, str):
                return resolve_string(value, stack)

            return value

        resolved = resolve_value(working, ())

        if not isinstance(resolved, dict):
            raise InterpolationError(
                "Interpolation changed the top-level Flow structure."
            )

        return self.model_validate(resolved)


class ExecutionResult(BaseModel):
    step_id: str
    status: StepStatus
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    peak_memory_mb: float = 0.0
    artifacts: list[Artifact] = Field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.start_time is not None and self.end_time is not None:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class FlowResult(BaseModel):
    flow_name: str
    run_id: str
    status: StepStatus
    step_results: dict[str, ExecutionResult] = Field(default_factory=dict)
    start_time: datetime | None = None
    end_time: datetime | None = None
