"""Point d'entrée principal du pipeline Mubawab."""
from mubawab_scraper.cli import app

__version__ = "0.1.0"

def main() -> None:
    """Entry point exposé via `mubawab-scraper` (script Typer)."""
    app()