import typer
from rich.console import Console

from mubawab_scraper.config import settings
from mubawab_scraper.logging_config import setup_logging
from mubawab_scraper.pipeline.orchestratior_ville import run_pipeline as run_pipeline_ville
from mubawab_scraper.pipeline.orchestrator import run_pipeline
from mubawab_scraper.pipeline.orchestrator_brut import (
    run_pipeline as run_pipeline_brut,
)

app = typer.Typer(help="Mubawab scraping pipeline", no_args_is_help=True)
console = Console()

@app.command()
def scrape(
    city: str = typer.Option(
        "casablanca",
        "--city",
        "--ville",
        help="Slug d'une ville, ou 'all' pour toutes les villes enregistrées",
    ),
    property_type: str = typer.Option(
        "all",
        help=(
            "Le motif /ct/ collecte tous les types de biens; "
            "seule la valeur 'all' est prise en charge"
        ),
    ),
    transaction: str = typer.Option(
        "a-vendre",
        "--transaction",
        "--action",
        help="a-vendre | a-louer | vacational | all",
    ),
    max_pages: int = typer.Option(
        settings.max_pages, help="Maximum pages per city; 0 scrapes every page"
    ),
    headless: bool = typer.Option(settings.headless),
    orchestrator: str = typer.Option(
        "default", help="default | ville | brut (scraping HTTP sans normalisation)"
    ),
) -> None:
    """Lance le pipeline complet."""
    setup_logging(settings.log_level)
    if orchestrator == "default":
        summaries = run_pipeline(
            city, property_type, transaction, max_pages, headless
        )
        total_listings = sum(summary.listings_scraped for summary in summaries)
        failed_actions = sum(summary.error is not None for summary in summaries)
        for summary in summaries:
            if summary.error:
                console.print(
                    f"[red]Échec {summary.city} ({summary.action}) : "
                    f"{summary.error}[/red]"
                )
                continue
            console.print(
                f"[cyan]{summary.city}[/cyan] ({summary.action}) : "
                f"{summary.pages_scraped}/{summary.total_pages} pages parcourues, "
                f"{summary.listings_scraped}/{summary.total_results} annonces trouvées"
            )
        console.print(f"[green]✓ {total_listings} annonces enregistrées[/green]")
        if failed_actions:
            console.print(
                f"[red]⚠ {failed_actions} action(s) de scraping en échec[/red]"
            )
    elif orchestrator == "ville":
        villes = run_pipeline_ville(city, transaction, headless)
        console.print(f"[green]✓ {len(villes)} villes enregistrées[/green]")
    elif orchestrator == "brut":
        summaries = run_pipeline_brut(city, transaction, max_pages)
        total_listings = sum(summary.listings_scraped for summary in summaries)
        for summary in summaries:
            if summary.error:
                console.print(
                    f"[red]Échec brut {summary.city} ({summary.action}) : "
                    f"{summary.error}[/red]"
                )
                continue
            console.print(
                f"[cyan]{summary.city}[/cyan] ({summary.action}) : "
                f"{summary.pages_scraped} pages parcourues, "
                f"{summary.listings_scraped} annonces brutes enregistrées"
            )
        console.print(f"[green]✓ {total_listings} annonces brutes enregistrées[/green]")
    else:
        raise typer.BadParameter(
            "orchestrator doit être 'default', 'ville' ou 'brut'"
        )

@app.command()
def export(
    fmt: str = typer.Option("csv", help="csv | parquet | json"),
    raw: bool = typer.Option(False, "--raw", help="Exporter les annonces brutes"),
) -> None:
    """Exporte la base vers un fichier plat."""
    from mubawab_scraper.storage.csv_store import export as _export, export_raw
    path = export_raw(fmt=fmt) if raw else _export(fmt=fmt)
    console.print(f"[green]✓ Export → {path}[/green]")

if __name__ == "__main__":
    app()