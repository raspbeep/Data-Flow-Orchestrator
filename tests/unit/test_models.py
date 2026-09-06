from pathlib import Path

import pytest
from pydantic import ValidationError

from dfo.core.models import Flow, Step

YAML_EXAMPLES = Path(__file__).parents[1] / "yaml_examples"


def test_from_yaml_parses_steps_as_models() -> None:
    flow = Flow.from_yaml(YAML_EXAMPLES / "basic.yaml")

    assert [step.id for step in flow.steps] == ["rtl_gen", "sim"]
    assert all(isinstance(step, Step) for step in flow.steps)


def test_interpolate_preserves_flow_structure_and_resolves_references() -> None:
    flow = Flow.from_yaml(YAML_EXAMPLES / "interpolation.yaml").interpolate()

    assert flow.name == "interpolation_flow"
    assert [step.id for step in flow.steps] == ["rtl_gen", "sim"]
    assert flow.get_step("rtl_gen").params["output_dir"] == "./build/rtl"
    assert flow.get_step("sim").params["rtl_location"] == "./build/rtl/cpu.v"


def test_duplicate_step_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Duplicate ids in steps: \\['gen'\\]"):
        Flow.from_yaml(YAML_EXAMPLES / "duplicate_steps.yaml")
