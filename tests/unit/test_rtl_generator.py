from pathlib import Path

import pytest

from dfo.core.models import StepStatus
from dfo.plugins.base import ExecutionContext
from dfo.plugins.rtl_generator import RTLGeneratorPlugin


def test_plugin_metadata() -> None:
    plugin = RTLGeneratorPlugin()

    assert plugin.name == "rtl_generator"
    assert plugin.version == "1.0.0"


def test_validate_params_accepts_required_params() -> None:
    plugin = RTLGeneratorPlugin()

    plugin.validate_params(
        {
            "arch": "rv64",
            "output_dir": "rtl",
        }
    )


def test_validate_params_rejects_missing_param() -> None:
    plugin = RTLGeneratorPlugin()

    with pytest.raises(ValueError, match="output_dir"):
        plugin.validate_params(
            {
                "arch": "rv64",
            }
        )


def test_run_generates_rtl_file(tmp_path: Path) -> None:
    plugin = RTLGeneratorPlugin()

    ctx = ExecutionContext(
        step_id="rtl_gen",
        params={
            "arch": "rv64",
            "output_dir": "rtl",
            "top_module": "cpu",
        },
        env={},
        workspace_dir=str(tmp_path),
    )

    result = plugin.run(ctx)

    assert result.status == StepStatus.SUCCESS
    assert result.returncode == 0

    rtl_file = tmp_path / "rtl" / "cpu.v"

    assert rtl_file.exists()
    assert "module cpu" in rtl_file.read_text()
