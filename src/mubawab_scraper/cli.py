import typer
from rich.console import Console
from mubawab_scraper.config import settings
from mubawab_scraper.logging_config import setup_logging
from mubawab_scraper.pipeline.orchestrator import run_pipeline
from mubawab_scraper.pipeline.orchestratior_ville import run_pipeline as run_pipeline_ville

app = typer.Typer(help="Mubawab scraping pipeline", no_args_is_help=True)
console = Console()

@app.command()
def scrape(
    city: str = typer.Option(
        "casablanca", help="Slug d'une ville, ou 'all' pour toutes les villes enregistrées"
    ),
    property_type: str = typer.Option("appartements"),
    transaction: str = typer.Option(
        "a-vendre", help="a-vendre | a-louer | vacational"
    ),
    max_pages: int = typer.Option(
        settings.max_pages, help="Maximum pages per city; 0 scrapes every page"
    ),
    headless: bool = typer.Option(settings.headless),
    orchestrator: str = typer.Option("default", help="default | ville"),
) -> None:
    """Lance le pipeline complet."""
    setup_logging(settings.log_level)
    if orchestrator == "default":
        summaries = run_pipeline(
            city, property_type, transaction, max_pages, headless
        )
        total_listings = sum(summary.listings_scraped for summary in summaries)
        for summary in summaries:
            console.print(
                f"[cyan]{summary.city}[/cyan] : "
                f"{summary.pages_scraped}/{summary.total_pages} pages parcourues, "
                f"{summary.listings_scraped}/{summary.total_results} annonces trouvées"
            )
        console.print(f"[green]✓ {total_listings} annonces enregistrées[/green]")
    elif orchestrator == "ville":
        villes = run_pipeline_ville(city, transaction, headless)
        console.print(f"[green]✓ {len(villes)} villes enregistrées[/green]")
    else:
        raise typer.BadParameter("orchestrator doit être 'default' ou 'ville'")

@app.command()
def export(fmt: str = typer.Option("csv", help="csv | parquet | json")) -> None:
    """Exporte la base vers un fichier plat."""
    from mubawab_scraper.storage.csv_store import export as _export
    path = _export(fmt=fmt)
    console.print(f"[green]✓ Export → {path}[/green]")

if __name__ == "__main__":
    app()