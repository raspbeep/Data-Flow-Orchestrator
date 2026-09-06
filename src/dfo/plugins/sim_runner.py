import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dfo.core.models import ExecutionResult, StepStatus
from dfo.plugins.base import ExecutionContext, Plugin


class SimRunnerPlugin(Plugin):
    @property
    def name(self) -> str:
        return "sim_runner"

    @property
    def version(self) -> str:
        return "1.0.0"

    def run(self, ctx: ExecutionContext) -> ExecutionResult:
        start_time = datetime.now()

        if ctx.dry_run:
            return ExecutionResult(
                step_id=ctx.step_id,
                status=StepStatus.SKIPPED,
                start_time=start_time,
                end_time=datetime.now(),
            )

        workspace = Path(ctx.workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)

        timeout = int(ctx.params.get("timeout", 300))

        try:
            result = subprocess.run(
                [sys.executable, "-c", 'print("simulation complete")'],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workspace,
            )

            return ExecutionResult(
                step_id=ctx.step_id,
                status=(
                    StepStatus.SUCCESS if result.returncode == 0 else StepStatus.FAILED
                ),
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                start_time=start_time,
                end_time=datetime.now(),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                step_id=ctx.step_id,
                status=StepStatus.FAILED,
                stderr=f"Simulation timed out after {timeout} seconds.",
                start_time=start_time,
                end_time=datetime.now(),
            )
