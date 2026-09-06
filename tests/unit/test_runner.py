from pathlib import Path
from unittest.mock import MagicMock

from dfo.core.models import (
    ExecutionResult,
    Flow,
    Step,
    StepStatus,
)
from dfo.core.runner import Runner
from dfo.plugins.base import ExecutionContext


def test_topological_sort(tmp_path: Path) -> None:
    flow = Flow(
        name="test",
        steps=[
            Step(id="gen", tool="rtl_generator"),
            Step(
                id="lint",
                tool="linter",
                depends_on=["gen"],
            ),
            Step(
                id="sim",
                tool="sim_runner",
                depends_on=["lint"],
            ),
        ],
    )

    runner = Runner(flow, workspace_dir=tmp_path)

    order = runner._topological_sort()

    assert order == ["gen", "lint", "sim"]


def test_execute_success(tmp_path: Path) -> None:
    flow = Flow(
        name="test",
        steps=[
            Step(id="a", tool="fake"),
            Step(id="b", tool="fake", depends_on=["a"]),
        ],
    )

    runner = Runner(flow, workspace_dir=tmp_path)

    fake_plugin = MagicMock()

    def fake_run(ctx: ExecutionContext) -> ExecutionResult:
        return ExecutionResult(
            step_id=ctx.step_id,
            status=StepStatus.SUCCESS,
            returncode=0,
        )

    fake_plugin.run.side_effect = fake_run

    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_plugin

    runner.registry = fake_registry

    result = runner.execute(run_id="test-run")

    assert result.status == StepStatus.SUCCESS
    assert result.step_results["a"].status == StepStatus.SUCCESS
    assert result.step_results["b"].status == StepStatus.SUCCESS


def test_failed_step_skips_dependents_but_runs_independent_steps(
    tmp_path: Path,
) -> None:
    flow = Flow(
        name="failure_flow",
        steps=[
            Step(id="a", tool="fake"),
            Step(id="b", tool="fake", depends_on=["a"]),
            Step(id="c", tool="fake", depends_on=["b"]),
            Step(id="d", tool="fake"),
        ],
    )

    runner = Runner(
        flow,
        workspace_dir=tmp_path,
    )

    fake_plugin = MagicMock()

    def fake_run(ctx: ExecutionContext) -> ExecutionResult:
        if ctx.step_id == "a":
            return ExecutionResult(
                step_id="a",
                status=StepStatus.FAILED,
                returncode=1,
            )

        return ExecutionResult(
            step_id=ctx.step_id,
            status=StepStatus.SUCCESS,
            returncode=0,
        )

    fake_plugin.run.side_effect = fake_run

    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_plugin

    runner.registry = fake_registry

    result = runner.execute(
        run_id="test-run",
    )

    assert result.status == StepStatus.FAILED

    assert result.step_results["a"].status == StepStatus.FAILED
    assert result.step_results["b"].status == StepStatus.SKIPPED
    assert result.step_results["c"].status == StepStatus.SKIPPED
    assert result.step_results["d"].status == StepStatus.SUCCESS

    assert fake_plugin.run.call_count == 2
