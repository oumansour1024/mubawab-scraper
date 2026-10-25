import typer
from rich.console import Console

from mubawab_scraper.config import settings
from mubawab_scraper.logging_config import setup_logging
from mubawab_scraper.pipeline.orchestratior_ville import run_pipeline as run_pipeline_ville
from mubawab_scraper.pipeline.orchestrator import run_pipeline
from mubawab_scraper.pipeline.orchestrator_brut import (
    MAX_RAW_WORKERS,
)
from mubawab_scraper.pipeline.orchestrator_brut import (
    run_pipeline as run_pipeline_brut,
)

app = typer.Typer(help="Mubawab scraping pipeline", no_args_is_help=True)
console = Console()


def _parse_page_range(value: str) -> tuple[int, int]:
    """Parse an inclusive page range such as ``v1:5``."""
    try:
        start_text, end_text = value.strip().lower().removeprefix("v").split(":")
        start, end = int(start_text), int(end_text)
    except ValueError as exc:
        raise typer.BadParameter(
            "Format de plage invalide; utilisez v1:5 (pages incluses)"
        ) from exc
    if start < 1 or end < start:
        raise typer.BadParameter("La plage de pages doit commencer à 1 ou plus et être croissante")
    return start, end


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
    workers: int = typer.Option(
        1,
        min=1,
        max=MAX_RAW_WORKERS,
        help="Nombre de tâches ville/action parallèles pour l'orchestrateur brut",
    ),
    city_range: str | None = typer.Option(
        None,
        "--city-range",
        help="Plage de villes enregistrées, ex. 'Casablanca;' jusqu'à la dernière",
    ),
    page_range: str | None = typer.Option(
        None,
        "--page-range",
        help="Plage inclusive de pages pour l'orchestrateur brut, ex. v1:5",
    ),
) -> None:
    """Lance le pipeline complet."""
    setup_logging(settings.log_level)
    if orchestrator == "default":
        if city_range is not None or page_range is not None:
            raise typer.BadParameter("--city-range et --page-range nécessitent --orchestrator brut")
        if workers != 1:
            raise typer.BadParameter(
                "--workers > 1 est uniquement pris en charge avec --orchestrator brut"
            )
        summaries = run_pipeline(city, property_type, transaction, max_pages, headless)
        total_listings = sum(summary.listings_scraped for summary in summaries)
        failed_actions = sum(summary.error is not None for summary in summaries)
        for summary in summaries:
            if summary.error:
                console.print(
                    f"[red]Échec {summary.city} ({summary.action}) : {summary.error}[/red]"
                )
                continue
            console.print(
                f"[cyan]{summary.city}[/cyan] ({summary.action}) : "
                f"{summary.pages_scraped}/{summary.total_pages} pages parcourues, "
                f"{summary.listings_scraped}/{summary.total_results} annonces trouvées"
            )
        console.print(f"[green]✓ {total_listings} annonces enregistrées[/green]")
        if failed_actions:
            console.print(f"[red]⚠ {failed_actions} action(s) de scraping en échec[/red]")
    elif orchestrator == "ville":
        if city_range is not None or page_range is not None:
            raise typer.BadParameter("--city-range et --page-range nécessitent --orchestrator brut")
        if workers != 1:
            raise typer.BadParameter(
                "--workers > 1 est uniquement pris en charge avec --orchestrator brut"
            )
        villes = run_pipeline_ville(city, transaction, headless)
        console.print(f"[green]✓ {len(villes)} villes enregistrées[/green]")
    elif orchestrator == "brut":
        parsed_page_range = _parse_page_range(page_range) if page_range is not None else None
        if city_range is None and parsed_page_range is None:
            raw_summaries = run_pipeline_brut(city, transaction, max_pages, workers=workers)
        else:
            raw_summaries = run_pipeline_brut(
                city,
                transaction,
                max_pages,
                workers=workers,
                city_range=city_range,
                page_range=parsed_page_range,
            )
        total_listings = sum(summary.listings_scraped for summary in raw_summaries)
        for raw_summary in raw_summaries:
            if raw_summary.error:
                console.print(
                    f"[red]Échec brut {raw_summary.city} ({raw_summary.action}) : "
                    f"{raw_summary.error}[/red]"
                )
                continue
            console.print(
                f"[cyan]{raw_summary.city}[/cyan] ({raw_summary.action}) : "
                f"{raw_summary.pages_scraped} pages parcourues, "
                f"{raw_summary.listings_scraped} annonces brutes enregistrées"
            )
        console.print(f"[green]✓ {total_listings} annonces brutes enregistrées[/green]")
    else:
        raise typer.BadParameter("orchestrator doit être 'default', 'ville' ou 'brut'")


@app.command()
def export(
    fmt: str = typer.Option("csv", help="csv | parquet | json"),
    raw: bool = typer.Option(False, "--raw", help="Exporter les annonces brutes"),
    details: bool = typer.Option(
        False,
        "--details",
        help="Exporter les annonces brutes et leurs détails",
    ),
) -> None:
    """Exporte la base vers un fichier plat."""
    from mubawab_scraper.storage.csv_store import (
        export as _export,
    )
    from mubawab_scraper.storage.csv_store import (
        export_raw,
        export_raw_details,
    )

    if details:
        paths = export_raw_details(fmt=fmt)
    elif raw:
        paths = [export_raw(fmt=fmt)]
    else:
        paths = [_export(fmt=fmt)]
    console.print(f"[green]✓ Export → {', '.join(paths)}[/green]")


@app.command()
def initdb() -> None:
    """Initialise ou migre les tables SQLite du pipeline brut."""
    from mubawab_scraper.storage.raw_store import RawListingStore
    from mubawab_scraper.storage.sqlite_store import SQLiteStore

    setup_logging(settings.log_level)
    normalized_store = SQLiteStore(settings.db_path)
    normalized_store.close()
    raw_store = RawListingStore(settings.db_path)
    raw_store.close()
    console.print(f"[green]✓ DB initialisée → {settings.db_path}[/green]")


@app.command()
def details(
    transaction: str = typer.Option(
        "all",
        "--transaction",
        "--action",
        help="a-vendre | a-louer | vacational | all",
    ),
    city: str = typer.Option(
        "all",
        "--city",
        "--ville",
        help="Ville ou all",
    ),
    limit: int = typer.Option(0, help="Nombre maximal d'URLs; 0 = toutes"),
    headless: bool = typer.Option(settings.headless),
    workers: int = typer.Option(
        1,
        min=1,
        max=4,
        help="Nombre de navigateurs parallèles (1 ou 4; limite prudente)",
    ),
) -> None:
    """Scrape les pages détail des annonces brutes non encore traitées."""
    from mubawab_scraper.pipeline.detail_pipeline import run_detail_pipeline

    setup_logging(settings.log_level)
    summary = run_detail_pipeline(
        transaction_type=transaction,
        city=city,
        limit=limit,
        headless=headless,
        workers=workers,
    )
    rate_limit_status = "non"
    if summary.rate_limited:
        rate_limit_status = "oui"
        if summary.retry_after:
            rate_limit_status += f" (Retry-After: {summary.retry_after})"
    console.print(
        f"[cyan]URLs trouvées :[/cyan] {summary.urls_found}\n"
        f"[green]Détails scrapés :[/green] {summary.details_scraped}\n"
        f"[red]Échecs :[/red] {summary.details_failed}\n"
        f"[yellow]Limitation HTTP 429 :[/yellow] {rate_limit_status}\n"
        f"[yellow]Durée :[/yellow] {summary.duration_sec:.1f}s"
    )


if __name__ == "__main__":
    app()
