from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from dfo.core.models import ExecutionResult


class ExecutionContext(BaseModel):
    step_id: str
    params: dict[str, Any]
    env: dict[str, str]
    workspace_dir: str
    dry_run: bool = False


class Plugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def run(self, ctx: ExecutionContext) -> ExecutionResult: ...

    def validate_params(self, params: dict[str, Any]) -> None:
        """Accept parameters by default; plugins may override to enforce a schema."""
        return None
