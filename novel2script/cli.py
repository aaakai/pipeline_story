from __future__ import annotations

from pathlib import Path

import typer

from .pipeline import Novel2ScriptPipeline
from .validators import validate_story_file


app = typer.Typer(add_completion=False, help="Convert novel text files into structured script JSON.")


@app.command()
def run(
    input_path: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    output_dir: Path = typer.Option(Path("./output_check"), "--output-dir", "-o", resolve_path=True),
    step: str = typer.Option("all", "--step", help="ingest | scenes | shots | all"),
    mock: bool = typer.Option(False, "--mock", help="Use deterministic mock client."),
    model: str | None = typer.Option(None, "--model", help="Model name for OpenAI-compatible mode."),
    base_url: str | None = typer.Option(None, "--base-url", help="Override OPENAI_BASE_URL."),
    api_key: str | None = typer.Option(None, "--api-key", help="Override OPENAI_API_KEY."),
    timeout_sec: int = typer.Option(60, "--timeout-sec", help="Request timeout in seconds."),
) -> None:
    if step not in {"ingest", "scenes", "shots", "all"}:
        raise typer.BadParameter("step must be one of: ingest, scenes, shots, all")

    pipeline = Novel2ScriptPipeline.from_config(
        output_dir=output_dir,
        use_mock=mock,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_sec=timeout_sec,
    )
    report = pipeline.run(input_path=input_path, step=step, use_mock=mock)
    if report.success:
        typer.echo(f"Pipeline finished successfully. Output: {report.output_dir}")
    else:
        typer.echo(f"Pipeline failed. See report: {Path(report.output_dir) / 'run_report.json'}", err=True)
        raise typer.Exit(code=1)


@app.command()
def validate(
    script_path: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
) -> None:
    errors = validate_story_file(script_path)
    if errors:
        typer.echo("Validation failed:")
        for item in errors:
            typer.echo(f"- {item}")
        raise typer.Exit(code=1)
    typer.echo("Validation passed.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
