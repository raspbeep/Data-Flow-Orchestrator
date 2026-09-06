from __future__ import annotations

import uuid
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from dfo.core.models import Flow, StepStatus
from dfo.core.runner import Runner
from dfo.core.state import StateStore
from dfo.marketplace.discovery import PluginRegistry

app = typer.Typer(
    name="dfo",
    help="Design Flow Orchestrator for RTL workflows.",
    no_args_is_help=True,
)

marketplace_app = typer.Typer(
    help="Discover and inspect installed DFO plugins.",
)

app.add_typer(
    marketplace_app,
    name="marketplace",
)

console = Console()


@app.command()
def run(
    flow_file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to the flow YAML file.",
        ),
    ],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Directory in which execution state and artifacts are stored.",
        ),
    ] = Path("./runs"),
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Resolve and validate the flow without executing real tool work.",
        ),
    ] = False,
) -> None:
    """Execute a design flow."""

    try:
        flow = Flow.from_yaml(flow_file)

        # Resolve ${...} references before execution.
        flow = flow.interpolate()

        run_id = uuid.uuid4().hex[:8]

        runner = Runner(
            flow=flow,
            workspace_dir=workspace,
        )

        result = runner.execute(
            run_id=run_id,
            dry_run=dry_run,
        )

    except Exception as exc:
        console.print(f"[bold red]Flow execution failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title=f"Flow: {result.flow_name} | Run: {result.run_id}")

    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Return code")
    table.add_column("Duration")

    for step_id, step_result in result.step_results.items():
        return_code = (
            str(step_result.returncode) if step_result.returncode is not None else "-"
        )

        table.add_row(
            step_id,
            step_result.status.value,
            return_code,
            f"{step_result.duration_seconds:.2f}s",
        )

    console.print(table)

    console.print(f"\nRun ID: [bold]{result.run_id}[/bold]")
    console.print(f"Flow status: [bold]{result.status.value}[/bold]")

    if result.status == StepStatus.FAILED:
        raise typer.Exit(code=1)


@app.command()
def status(
    run_id: Annotated[str, typer.Argument(help="ID of the run to inspect.")],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Workspace containing the DFO state database.",
        ),
    ] = Path("./runs"),
) -> None:
    """Show the status of a previous run."""

    store = StateStore(workspace / ".dfo_state.db")

    result = store.get_run(run_id)

    if result is None:
        console.print(f"[red]Run '{run_id}' was not found.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Flow:[/bold] {result.flow_name}")
    console.print(f"[bold]Run ID:[/bold] {result.run_id}")
    console.print(f"[bold]Status:[/bold] {result.status.value}")

    if result.start_time is not None:
        console.print(f"[bold]Started:[/bold] {result.start_time}")

    if result.end_time is not None:
        console.print(f"[bold]Finished:[/bold] {result.end_time}")

    if not result.step_results:
        return

    table = Table(title="Step results")

    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Return code")
    table.add_column("Duration")

    for step_id, step_result in result.step_results.items():
        return_code = (
            str(step_result.returncode) if step_result.returncode is not None else "-"
        )

        table.add_row(
            step_id,
            step_result.status.value,
            return_code,
            f"{step_result.duration_seconds:.2f}s",
        )

    console.print(table)


@app.command("init")
def init_flow(
    name: Annotated[
        str, typer.Option("--name", "-n", help="Name of the generated flow.")
    ] = "my_flow",
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Path at which to create the YAML file."),
    ] = Path("flow.yaml"),
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing file.")
    ] = False,
) -> None:
    """Create a starter flow YAML file."""

    if output.exists() and not force:
        console.print(f"[red]'{output}' already exists.[/red]")
        console.print("Use --force if you want to overwrite it.")
        raise typer.Exit(code=1)

    template = f"""\
name: {name}
version: "1.0.0"

environment:
  OUT_ROOT: ./out

steps:
  - id: rtl_gen
    tool: rtl_generator
    params:
      arch: rv64
      output_dir: ${{env.OUT_ROOT}}/rtl
      top_module: cpu
    artifacts:
      - ${{env.OUT_ROOT}}/rtl/*.v

  - id: sim
    tool: sim_runner
    depends_on:
      - rtl_gen
    params:
      timeout: 30
"""

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(template)

    console.print(f"[green]Created flow file:[/green] {output}")


@marketplace_app.command("list")
def marketplace_list() -> None:
    """List installed DFO plugins."""

    registry = PluginRegistry()
    registry.discover()

    plugins = registry.list_plugins()

    if not plugins:
        console.print("[yellow]No plugins were discovered.[/yellow]")
        return

    table = Table(title="Installed plugins")

    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Class")

    for name, plugin in plugins.items():
        table.add_row(
            name,
            plugin.version,
            plugin.__class__.__name__,
        )

    console.print(table)


@marketplace_app.command("info")
def marketplace_info(
    name: Annotated[str, typer.Argument(help="Name of the plugin to inspect.")],
) -> None:
    """Show information about an installed plugin."""

    registry = PluginRegistry()
    registry.discover()

    try:
        plugin = registry.get(name)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Name:[/bold] {plugin.name}")
    console.print(f"[bold]Version:[/bold] {plugin.version}")
    console.print(f"[bold]Class:[/bold] {plugin.__class__.__name__}")


@app.command()
def version() -> None:
    """Show the installed DFO version."""

    try:
        installed_version = package_version("dfo")
    except PackageNotFoundError:
        installed_version = "unknown"

    console.print(f"dfo {installed_version}")


if __name__ == "__main__":
    app()
