from datetime import datetime
from pathlib import Path
from typing import Any

from dfo.core.models import ExecutionResult, StepStatus
from dfo.plugins.base import ExecutionContext, Plugin


class RTLGeneratorPlugin(Plugin):
    @property
    def name(self) -> str:
        return "rtl_generator"

    @property
    def version(self) -> str:
        return "1.0.0"

    def validate_params(self, params: dict[str, Any]) -> None:
        required = {"arch", "output_dir"}
        provided = set(params)
        missing = required - provided
        if missing:
            raise ValueError(
                f"Missing required RTLGeneratorPlugin parameter(s) [{missing}]"
            )

    def run(self, ctx: ExecutionContext) -> ExecutionResult:
        start_time = datetime.now()

        if ctx.dry_run:
            return ExecutionResult(
                step_id=ctx.step_id,
                status=StepStatus.SKIPPED,
                start_time=start_time,
                end_time=datetime.now(),
            )

        output_dir = Path(Path(ctx.workspace_dir) / ctx.params["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        top_module = str(ctx.params.get("top_module", "top"))

        rtl_content = f"""
module {top_module}(
    input  wire a,
    input  wire b,
    output wire y
);

assign y = a & b;

endmodule
        """

        rtl_file = output_dir / f"{top_module}.v"
        rtl_file.write_text(rtl_content)

        return ExecutionResult(
            step_id=ctx.step_id,
            status=StepStatus.SUCCESS,
            stdout=f"Generated {rtl_file}",
            returncode=0,
            start_time=start_time,
            end_time=datetime.now(),
        )
