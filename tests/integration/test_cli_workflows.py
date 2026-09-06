import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dfo.cli.main import app

YAML_EXAMPLES = Path(__file__).resolve().parents[1] / "yaml_examples"


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


def test_run_basic_then_status(cli_runner: CliRunner, tmp_path: Path) -> None:
    workspace = tmp_path / "runs"
    result = cli_runner.invoke(
        app,
        ["run", str(YAML_EXAMPLES / "basic.yaml"), "--workspace", str(workspace)],
        color=False,
    )

    assert result.exit_code == 0, result.output
    assert "Flow status: success" in result.output
    match = re.search(r"^\s*Run ID:\s*([0-9a-f]+)\s*$", result.output, re.MULTILINE)
    assert match is not None, result.output
    run_id = match.group(1)
    rtl_file = workspace / run_id / "rtl_gen" / "out" / "rtl" / "cpu.v"
    assert "module cpu(" in rtl_file.read_text()

    database = workspace / ".dfo_state.db"
    assert database.is_file()
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute(
            "SELECT flow_name, status FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone() == ("basic_rtl_flow", "success")
        assert connection.execute(
            "SELECT step_id, status FROM step_results WHERE run_id = ? ORDER BY step_id",
            (run_id,),
        ).fetchall() == [("rtl_gen", "success"), ("sim", "success")]

    status = cli_runner.invoke(
        app, ["status", run_id, "--workspace", str(workspace)], color=False
    )

    assert status.exit_code == 0, status.output
    assert "Flow: basic_rtl_flow" in status.output
    assert f"Run ID: {run_id}" in status.output
    assert "Status: success" in status.output
    for step_id in ("rtl_gen", "sim"):
        assert re.search(
            rf"\b{step_id}\b[^\n]*\bsuccess\b", status.output
        ), status.output


def test_status_unknown_run(cli_runner: CliRunner, tmp_path: Path) -> None:
    result = cli_runner.invoke(
        app,
        ["status", "unknown-run", "--workspace", str(tmp_path / "runs")],
        color=False,
    )

    assert result.exit_code == 1, result.output
    assert "Run 'unknown-run' was not found." in result.output


@pytest.mark.parametrize(
    ("example", "error_fragment", "creates_workspace"),
    [
        ("bad_dependency", "depends on an unknown step", False),
        ("bad_interpolation", "Could not find the key for the reference", False),
        ("cyclic", "Dependency cycle detected", False),
        ("duplicate_steps", "Duplicate ids in steps", False),
        ("interpolation_cycle", "Detected a cycle during value interpolation", False),
        ("missing_params", "Missing required RTLGeneratorPlugin parameter(s)", True),
        ("missing_plugin", "Plugin 'magical_synthesis_tool' not found", True),
    ],
)
def test_run_invalid_example(
    cli_runner: CliRunner,
    tmp_path: Path,
    example: str,
    error_fragment: str,
    creates_workspace: bool,
) -> None:
    workspace = tmp_path / "runs"
    result = cli_runner.invoke(
        app,
        ["run", str(YAML_EXAMPLES / f"{example}.yaml"), "--workspace", str(workspace)],
        color=False,
    )

    assert result.exit_code == 1, result.output
    output = " ".join(result.output.split())
    assert "Flow execution failed:" in output
    assert error_fragment in output
    assert not list(tmp_path.rglob("*.v"))

    if creates_workspace:
        database = workspace / ".dfo_state.db"
        assert database.is_file()
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute(
                "SELECT status, end_time IS NOT NULL FROM runs"
            ).fetchall() == [("failed", 1)]
    else:
        assert not workspace.exists()
