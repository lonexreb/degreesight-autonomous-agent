"""MorningStar CLI -- the main entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from morningstar import __version__
from morningstar.banner import print_banner
from morningstar.engine import (
    RunState,
    execute_task,
    fetch_prd,
    generate_tasks,
    slack_post,
)

app = typer.Typer(
    name="morningstar",
    help="Autonomous coding agent powered by Claude Code.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def _status_panel(state: RunState, total: int, current_task: str = "") -> Panel:
    """Build a live status panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")

    done = state.completed + state.failed
    table.add_row("Progress", f"{done}/{total} tasks")
    table.add_row("Completed", f"[green]{state.completed}[/green]")
    table.add_row("Failed", f"[red]{state.failed}[/red]")
    table.add_row("Cost", f"[yellow]${state.cost:.2f}[/yellow]")

    if current_task:
        table.add_row("Current", f"[cyan]{current_task}[/cyan]")

    return Panel(
        table,
        title="[bold bright_yellow]MorningStar[/bold bright_yellow]",
        border_style="bright_yellow",
        padding=(1, 2),
    )


@app.command()
def run(
    notion_url: str = typer.Option(
        ...,
        "--notion-url",
        "-n",
        help="Notion page URL or ID containing the PRD.",
    ),
    slack_webhook: str = typer.Option(
        ...,
        "--slack-webhook",
        "-s",
        help="Slack incoming webhook URL for status updates.",
    ),
    repo: Path = typer.Option(
        ...,
        "--repo",
        "-r",
        help="Path to the target repository.",
        exists=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    model: str = typer.Option(
        "sonnet",
        "--model",
        "-m",
        help="Claude model to use.",
    ),
    budget: float = typer.Option(
        50.0,
        "--budget",
        "-b",
        help="Total USD budget for the run.",
    ),
    budget_per_task: float = typer.Option(
        5.0,
        "--task-budget",
        help="Max USD per task.",
    ),
) -> None:
    """Run the autonomous coding agent.

    Reads a PRD from Notion, analyzes the target repo, generates tasks,
    and implements each one using Claude Code CLI.
    """
    print_banner(console)

    repo_path = repo.resolve()
    log_dir = repo_path / ".agent-logs"
    log_dir.mkdir(exist_ok=True)

    state = RunState()

    # ── Step 1: Fetch PRD ─────────────────────────────────────────
    with console.status("[bold yellow]Fetching PRD from Notion...", spinner="star"):
        slack_post(slack_webhook, "MorningStar started. Reading PRD from Notion...")
        try:
            prd_text = fetch_prd(
                notion_url,
                model=model,
                log_dir=log_dir,
                console=console,
            )
        except RuntimeError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            slack_post(slack_webhook, f"MorningStar failed: {e}")
            raise typer.Exit(1)

    lines = prd_text.count("\n") + 1
    console.print(
        f"  [green]PRD fetched[/green] ({lines} lines)",
    )

    # ── Step 2: Generate tasks ────────────────────────────────────
    with console.status("[bold yellow]Analyzing codebase & generating tasks...", spinner="star"):
        slack_post(slack_webhook, "PRD loaded. Analyzing codebase...")
        try:
            tasks = generate_tasks(
                prd_text,
                repo_path=repo_path,
                model=model,
                log_dir=log_dir,
                console=console,
            )
        except RuntimeError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            slack_post(slack_webhook, f"MorningStar failed: {e}")
            raise typer.Exit(1)

    task_count = len(tasks)
    state.tasks = tasks
    console.print(f"  [green]Generated {task_count} tasks[/green]")
    console.print()

    # Show task list
    task_table = Table(
        title="Task Plan",
        border_style="bright_yellow",
        show_lines=True,
    )
    task_table.add_column("#", style="dim", width=4)
    task_table.add_column("ID", style="cyan")
    task_table.add_column("Title", style="white")

    for i, t in enumerate(tasks, 1):
        task_table.add_row(str(i), t["id"], t["title"])

    console.print(task_table)
    console.print()

    slack_post(
        slack_webhook,
        f"Found {task_count} tasks to implement. Starting work...",
    )

    # ── Step 3: Execute tasks ─────────────────────────────────────
    progress = Progress(
        SpinnerColumn("star", style="yellow"),
        TextColumn("[bold]{task.fields[task_title]}"),
        BarColumn(bar_width=30, style="yellow", complete_style="green"),
        TextColumn("[dim]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        overall = progress.add_task(
            "Running",
            total=task_count,
            task_title="MorningStar",
        )

        for i, task in enumerate(tasks):
            task_id = task["id"]
            title = task["title"]

            # Budget check
            if state.cost >= budget:
                console.print(
                    f"\n[bold red]Budget limit reached[/bold red] "
                    f"(${state.cost:.2f}/${budget:.2f})"
                )
                slack_post(
                    slack_webhook,
                    f"Budget limit reached (${state.cost:.2f}/${budget:.2f}). Stopping.",
                )
                break

            progress.update(overall, task_title=title)
            slack_post(slack_webhook, f"[{i + 1}/{task_count}] Starting: *{title}*")

            result = execute_task(
                task,
                repo_path=repo_path,
                model=model,
                budget_per_task=budget_per_task,
                log_dir=log_dir,
            )

            state.cost += result.cost

            if result.success:
                state.completed += 1
                progress.update(overall, advance=1)
                slack_post(
                    slack_webhook,
                    f"[{i + 1}/{task_count}] Completed: *{title}* (${result.cost:.2f})",
                )
            else:
                state.failed += 1
                progress.update(overall, advance=1)
                slack_post(
                    slack_webhook,
                    f"[{i + 1}/{task_count}] Failed: *{title}* (${result.cost:.2f})",
                )

    # ── Step 4: Summary ───────────────────────────────────────────
    console.print()

    summary = Table(
        title="Run Complete",
        border_style="bright_yellow",
        show_lines=True,
    )
    summary.add_column("Metric", style="dim")
    summary.add_column("Value", style="bold")

    summary.add_row("Tasks completed", f"[green]{state.completed}[/green]")
    summary.add_row("Tasks failed", f"[red]{state.failed}[/red]")
    summary.add_row("Total cost", f"[yellow]${state.cost:.2f}[/yellow]")
    summary.add_row("Budget", f"${budget:.2f}")
    summary.add_row("Logs", str(log_dir))

    console.print(summary)

    slack_post(
        slack_webhook,
        f"MorningStar complete: *{state.completed}* done, "
        f"*{state.failed}* failed. Cost: ${state.cost:.2f}/{budget:.2f}",
    )


@app.command()
def version() -> None:
    """Show MorningStar version."""
    print_banner(console)
    console.print(f"  Version: [bold]{__version__}[/bold]")


def main() -> None:
    app()
