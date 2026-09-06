import collections
from datetime import datetime
from pathlib import Path

from dfo.core.exceptions import CycleError
from dfo.core.models import ExecutionResult, Flow, FlowResult, Step, StepStatus
from dfo.core.state import StateStore
from dfo.marketplace.discovery import PluginRegistry
from dfo.plugins.base import ExecutionContext


class Runner:
    def __init__(self, flow: Flow, workspace_dir: str | Path = "./runs") -> None:
        self.flow = flow
        self.workspace_dir = Path(workspace_dir)

        self.registry = PluginRegistry()
        self.registry.discover()

        self.state = StateStore(self.workspace_dir / ".dfo_state.db")

    def _build_dag(self) -> tuple[dict[str, list[str]], dict[str, int]]:
        dependents: dict[str, list[str]] = {step.id: [] for step in self.flow.steps}

        in_degree = {step.id: len(step.depends_on) for step in self.flow.steps}

        for step in self.flow.steps:
            step_id = step.id
            step_dependencies = step.depends_on
            for dependency in step_dependencies:
                dependents[dependency].append(step_id)

        return dependents, in_degree

    def _topological_sort(self) -> list[str]:
        execution_order = []

        dependents, in_degree = self._build_dag()

        ready = collections.deque(
            step_id for step_id, degree in in_degree.items() if degree == 0
        )

        while ready:
            step_id = ready.popleft()
            execution_order.append(step_id)
            for dependent in dependents[step_id]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    ready.append(dependent)

        if len(execution_order) != len(self.flow.steps):
            raise CycleError("Dependency cycle detected.")

        return execution_order

    def _run_step(
        self, step: Step, run_id: str, dry_run: bool = False
    ) -> ExecutionResult:
        plugin = self.registry.get(step.tool)
        plugin.validate_params(step.params)

        env = {
            key: str(value) for key, value in self.flow.environment.model_dump().items()
        }

        step_workspace = self.workspace_dir / run_id / step.id

        ctx = ExecutionContext(
            step_id=step.id,
            params=step.params,
            env=env,
            workspace_dir=str(step_workspace),
            dry_run=dry_run,
        )

        result = plugin.run(ctx)

        self.state.save_step(
            run_id,
            result,
        )

        return result

    def execute(
        self,
        run_id: str,
        dry_run: bool = False,
    ) -> FlowResult:
        flow_result = FlowResult(
            flow_name=self.flow.name,
            run_id=run_id,
            status=StepStatus.RUNNING,
            start_time=datetime.now(),
        )

        # Persist immediately so the run exists even while execution is ongoing.
        self.state.save_run(flow_result)

        failed_or_skipped: set[str] = set()
        had_failure = False

        try:
            execution_order = self._topological_sort()

            for step_id in execution_order:
                step = self.flow.get_step(step_id)

                dependency_unavailable = any(
                    dependency in failed_or_skipped for dependency in step.depends_on
                )

                if dependency_unavailable:
                    step_result = ExecutionResult(
                        step_id=step.id,
                        status=StepStatus.SKIPPED,
                    )

                    flow_result.step_results[step.id] = step_result
                    failed_or_skipped.add(step.id)

                    # _run_step() wasn't called, so save this result ourselves.
                    self.state.save_step(
                        run_id,
                        step_result,
                    )

                    continue

                step_result = self._run_step(
                    step,
                    run_id,
                    dry_run,
                )

                flow_result.step_results[step.id] = step_result

                if step_result.status == StepStatus.FAILED:
                    failed_or_skipped.add(step.id)
                    had_failure = True

            if had_failure:
                flow_result.status = StepStatus.FAILED
            else:
                flow_result.status = StepStatus.SUCCESS

        except Exception:
            # An unexpected exception should never leave a persisted run
            # permanently marked as RUNNING.
            flow_result.status = StepStatus.FAILED
            raise

        finally:
            flow_result.end_time = datetime.now()
            self.state.save_run(flow_result)

        return flow_result
