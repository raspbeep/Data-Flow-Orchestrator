from pathlib import Path

import pytest
from typer.testing import CliRunner

from dfo.cli.main import app


@pytest.mark.parametrize(
    "command",
    [[], ["run"], ["status"], ["init"], ["marketplace", "info"]],
)
def test_command_help(command: list[str]) -> None:
    result = CliRunner().invoke(app, [*command, "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


def test_init_options_and_overwrite_protection(tmp_path: Path) -> None:
    runner = CliRunner()
    flow_path = tmp_path / "custom.yaml"
    args = ["init", "--name", "custom_flow", "--output", str(flow_path)]

    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    original = flow_path.read_text()
    assert "name: custom_flow" in original

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert flow_path.read_text() == original

    result = runner.invoke(app, [*args, "--force"])

    assert result.exit_code == 0, result.output


def test_run_dry_run_with_workspace_option(tmp_path: Path) -> None:
    runner = CliRunner()
    flow_path = tmp_path / "flow.yaml"
    workspace = tmp_path / "runs"
    initialized = runner.invoke(app, ["init", "--output", str(flow_path)])
    assert initialized.exit_code == 0, initialized.output

    result = runner.invoke(
        app,
        ["run", str(flow_path), "--workspace", str(workspace), "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "skipped" in result.output
    assert (workspace / ".dfo_state.db").is_file()
    assert not list(workspace.rglob("*.v"))
