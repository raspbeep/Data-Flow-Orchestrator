from datetime import datetime
from pathlib import Path

import pytest
from freezegun import freeze_time

from dfo.core.models import Flow, StepStatus
from dfo.core.runner import Runner
from dfo.core.state import StateStore

YAML_EXAMPLES = Path(__file__).parents[1] / "yaml_examples"


@pytest.mark.parametrize(
    ("example", "expected_rtl"),
    [
        ("basic.yaml", ["rtl_gen/out/rtl/cpu.v"]),
        ("interpolation.yaml", ["rtl_gen/build/rtl/cpu.v"]),
        ("branching.yaml", ["gen_a/out/a/cpu_a.v", "gen_b/out/b/cpu_b.v"]),
    ],
)
def test_example_flow_executes_and_round_trips_state(
    tmp_path: Path, example: str, expected_rtl: list[str]
) -> None:
    flow = Flow.from_yaml(YAML_EXAMPLES / example).interpolate()
    assert "${" not in flow.model_dump_json()
    if example == "interpolation.yaml":
        assert flow.get_step("sim").params["rtl_location"] == "./build/rtl/cpu.v"

    workspace = tmp_path / "runs"
    run_id = "integration-run"
    timestamp = datetime(2026, 9, 6, 12, 0, 0)

    # Freeze orchestration timestamps while still running the real simulator subprocess.
    with freeze_time(timestamp):
        result = Runner(flow, workspace_dir=workspace).execute(run_id=run_id)

    assert result.status == StepStatus.SUCCESS
    assert result.flow_name == flow.name
    assert result.run_id == run_id
    assert result.start_time == result.end_time == timestamp
    assert set(result.step_results) == {step.id for step in flow.steps}

    execution_order = list(result.step_results)
    for step in flow.steps:
        step_result = result.step_results[step.id]
        assert step_result.step_id == step.id
        assert step_result.status == StepStatus.SUCCESS
        assert step_result.returncode == 0
        assert step_result.stderr == ""
        assert step_result.start_time == step_result.end_time == timestamp
        assert step_result.duration_seconds == 0.0
        for dependency in step.depends_on:
            assert execution_order.index(dependency) < execution_order.index(step.id)
        if step.tool == "sim_runner":
            assert step_result.stdout == "simulation complete\n"

    run_dir = workspace / run_id
    generated_rtl = sorted(
        path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*.v")
    )
    assert generated_rtl == sorted(expected_rtl)
    for relative_path in expected_rtl:
        rtl_path = run_dir / relative_path
        assert f"module {rtl_path.stem}(" in rtl_path.read_text()
        assert "assign y = a & b;" in rtl_path.read_text()

    reopened_store = StateStore(workspace / ".dfo_state.db")
    assert reopened_store.get_run(run_id) == result
    for step_id, step_result in result.step_results.items():
        assert reopened_store.get_step_result(run_id, step_id) == step_result
    assert reopened_store.get_run("unknown-run") is None
    assert reopened_store.get_step_result(run_id, "unknown-step") is None
    assert reopened_store.get_step_result("unknown-run", flow.steps[0].id) is None
