"""
CLI entrypoint for fin-agent command (defined in pyproject.toml).

Usage:
  fin-agent ingest --source all --sample
  fin-agent status
  fin-agent serve
"""
import typer
from typing import Optional

from app.core.logging import configure_logging

configure_logging()
app = typer.Typer(
    name="fin-agent",
    help="Fin AI Agent CLI — manage ingestion, server, and status.",
    add_completion=False,
)


@app.command()
def ingest(
    source: str = typer.Option("all", help="cfpb | sec | policy | all"),
    sample: bool = typer.Option(False, "--sample", help="Use 5K sample for CFPB"),
    provider: str = typer.Option("openai", help="openai | local"),
) -> None:
    """Run the data ingestion pipeline."""
    from app.ingestion.pipeline import IngestionPipeline

    typer.echo(f"Starting ingestion: source={source}, sample={sample}, provider={provider}")
    pipeline = IngestionPipeline(embedding_provider=provider)  # type: ignore[arg-type]

    source_map = {
        "cfpb": lambda: pipeline.run_cfpb(sample_mode=sample),
        "sec": pipeline.run_sec,
        "policy": pipeline.run_policy,
        "all": lambda: pipeline.run_all(sample_cfpb=sample),
    }
    if source not in source_map:
        typer.echo(f"Unknown source: {source}. Choose from: cfpb, sec, policy, all", err=True)
        raise typer.Exit(1)

    stats = source_map[source]()
    typer.echo(f"Ingestion complete: {stats}")


@app.command()
def status() -> None:
    """Show current vector store document counts."""
    from app.ingestion.processors.vector_store import VectorStoreWriter
    from app.core.config import settings

    writer = VectorStoreWriter()
    counts = {
        "complaints": writer.collection_count(settings.qdrant_collection_complaints),
        "policies": writer.collection_count(settings.qdrant_collection_policies),
        "faq": writer.collection_count(settings.qdrant_collection_faq),
    }
    for name, count in counts.items():
        typer.echo(f"  {name:20s}: {count:,} vectors")
    typer.echo(f"  {'total':20s}: {sum(counts.values()):,} vectors")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
) -> None:
    """Start the FastAPI development server."""
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
