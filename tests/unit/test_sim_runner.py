from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import patch

from dfo.core.models import StepStatus
from dfo.plugins.base import ExecutionContext
from dfo.plugins.sim_runner import SimRunnerPlugin


def test_simulation_success(tmp_path: Path) -> None:
    plugin = SimRunnerPlugin()

    ctx = ExecutionContext(
        step_id="sim",
        params={"timeout": 10},
        env={},
        workspace_dir=str(tmp_path),
    )

    fake_result = CompletedProcess(
        args=["fake"],
        returncode=0,
        stdout="simulation complete\n",
        stderr="",
    )

    with patch(
        "dfo.plugins.sim_runner.subprocess.run",
        return_value=fake_result,
    ):
        result = plugin.run(ctx)

    assert result.status == StepStatus.SUCCESS
    assert result.returncode == 0
    assert result.stdout == "simulation complete\n"


def test_simulation_non_zero_exit(tmp_path: Path) -> None:
    plugin = SimRunnerPlugin()

    ctx = ExecutionContext(
        step_id="sim",
        params={"timeout": 10},
        env={},
        workspace_dir=str(tmp_path),
    )

    fake_result = CompletedProcess(
        args=["fake"],
        returncode=1,
        stdout="simulation FAILED\n",
        stderr="error message",
    )

    with patch(
        "dfo.plugins.sim_runner.subprocess.run",
        return_value=fake_result,
    ):
        result = plugin.run(ctx)

    assert result.status == StepStatus.FAILED
    assert result.returncode == 1
    assert result.stdout == "simulation FAILED\n"


def test_simulation_timeout_expired(tmp_path: Path) -> None:
    plugin = SimRunnerPlugin()

    ctx = ExecutionContext(
        step_id="sim",
        params={"timeout": 10},
        env={},
        workspace_dir=str(tmp_path),
    )

    side_effect = TimeoutExpired(
        cmd=["fake"],
        timeout=2,
    )

    with patch("dfo.plugins.sim_runner.subprocess.run", side_effect=side_effect):
        result = plugin.run(ctx)

    assert result.status == StepStatus.FAILED
    assert result.returncode is None
    assert "timed out" in result.stderr.lower()


def test_dry_run_does_not_launch_process(tmp_path: Path) -> None:
    plugin = SimRunnerPlugin()

    ctx = ExecutionContext(
        step_id="sim",
        params={"timeout": 10},
        env={},
        workspace_dir=str(tmp_path),
        dry_run=True,
    )

    with patch("dfo.plugins.sim_runner.subprocess.run") as mock_run:
        result = plugin.run(ctx)

    assert result.status == StepStatus.SKIPPED
    mock_run.assert_not_called()


def test_plugin_arguments(tmp_path: Path) -> None:
    plugin = SimRunnerPlugin()

    ctx = ExecutionContext(
        step_id="sim",
        params={"timeout": 10},
        env={},
        workspace_dir=str(tmp_path),
    )

    fake_result = CompletedProcess(
        args=["fake"],
        returncode=0,
        stdout="simulation FAILED\n",
        stderr="error message",
    )

    with patch(
        "dfo.plugins.sim_runner.subprocess.run",
        return_value=fake_result,
    ) as mock_run:
        result = plugin.run(ctx)

    _, kwargs = mock_run.call_args

    assert result.returncode == 0
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 10
    assert kwargs["cwd"] == tmp_path
