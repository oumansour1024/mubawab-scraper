"""
Configuration du logging pour Mubawab Scraper.

Branche ``structlog`` sur la bibliothèque standard ``logging`` et écrit
les logs simultanément :

- sur la **console** (stdout) — dev / Docker / K8s ;
- dans un **fichier rotatif** — persistance, debug post-mortem.

Deux stratégies de rotation sont disponibles :

- ``rotation="size"`` : un nouveau fichier tous les N Mo (défaut 10 Mo),
  avec N fichiers conservés.
- ``rotation="time"`` : un nouveau fichier par jour (ou heure/min), avec
  N jours conservés.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog
from structlog.types import Processor

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

_LEVELS: dict[str, int] = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _resolve_level(level: str | int) -> int:
    """
    Convertit un nom de niveau (``"INFO"``, ``"info"``, ``20``…) en entier
    ``logging``.

    :raises ValueError: Si le nom n'est pas reconnu.
    """
    if isinstance(level, int):
        return level
    try:
        return _LEVELS[level.upper()]
    except KeyError as exc:
        raise ValueError(
            f"Niveau de log inconnu: {level!r}. Attendu: {', '.join(_LEVELS)}."
        ) from exc


def _build_file_handler(
    log_dir: Path,
    *,
    rotation: str = "size",
    max_bytes: int = 10 * 1024 * 1024,  # 10 Mo
    backup_count: int = 7,
    filename: str | None = None,
) -> logging.Handler:
    """
    Construit un handler fichier rotatif.

    :param log_dir: Dossier de destination (créé si absent).
    :param rotation: ``"size"`` (par taille) ou ``"time"`` (par jour).
    :param max_bytes: Taille max avant rotation (mode ``"size"``).
    :param backup_count: Nombre de fichiers conservés (anciens supprimés).
    :param filename: Nom du fichier log. Par défaut
        ``mubawab_YYYY-MM-DD.log``.
    :return: Handler configuré.
    :raises ValueError: Si ``rotation`` est inconnu.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        filename = f"mubawab_{stamp}.log"

    path = log_dir / filename

    if rotation == "size":
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,  # n'ouvre le fichier qu'au 1er log
        )
    elif rotation == "time":
        handler = logging.handlers.TimedRotatingFileHandler(
            path,
            when="midnight",
            backupCount=backup_count,
            encoding="utf-8",
            utc=True,
            delay=True,
        )
        # Suffixe des anciens fichiers : mubawab.log.2026-10-13
        handler.suffix = "%Y-%m-%d"
    else:
        raise ValueError(f"Rotation inconnue: {rotation!r}. Attendu: 'size' ou 'time'.")

    return handler


# --------------------------------------------------------------------------- #
# API publique
# --------------------------------------------------------------------------- #


def setup_logging(
    level: str | int = "INFO",
    *,
    json_logs: bool = False,
    log_dir: str | Path | None = None,
    rotation: str = "size",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 7,
    console: bool = True,
    include_timestamp: bool = True,
) -> None:
    """
    Configure ``structlog`` + ``logging`` avec sortie console et/ou fichier.

    À appeler **une seule fois** au démarrage (CLI, FastAPI, tests).

    :param level: Niveau minimal — ``"DEBUG"``…``"CRITICAL"`` ou entier.
    :param json_logs: ``True`` → JSON (prod) ; ``False`` → console colorée (dev).
    :param log_dir: Dossier où stocker les fichiers log. ``None`` → pas
        d'écriture fichier (console uniquement).
    :param rotation: ``"size"`` (par taille) ou ``"time"`` (quotidienne).
    :param max_bytes: Taille max avant rotation (mode ``"size"``).
    :param backup_count: Nombre de fichiers anciens conservés.
    :param console: Écrire aussi sur stdout.
    :param include_timestamp: Ajouter un horodatage ISO 8601 aux events.
    :raises ValueError: Si ``level`` ou ``rotation`` est invalide.
    """
    numeric_level = _resolve_level(level)

    # ------------------------------------------------------------------ #
    # 1. Pipeline structlog (commun aux deux sorties)
    # ------------------------------------------------------------------ #
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if include_timestamp:
        shared_processors.insert(1, structlog.processors.TimeStamper(fmt="iso", utc=True))

    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=console)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )

    # ------------------------------------------------------------------ #
    # 2. Handlers stdlib
    # ------------------------------------------------------------------ #
    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Retire les handlers existants (évite les doublons au reload).
    for h in list(root.handlers):
        root.removeHandler(h)

    # Format neutre : structlog rend déjà tout le message.
    formatter = logging.Formatter("%(message)s")

    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(numeric_level)
        ch.setFormatter(formatter)
        root.addHandler(ch)

    if log_dir is not None:
        fh = _build_file_handler(
            Path(log_dir),
            rotation=rotation,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
        fh.setLevel(numeric_level)
        fh.setFormatter(formatter)
        root.addHandler(fh)

    # ------------------------------------------------------------------ #
    # 3. Libs bruyantes (optionnel — décommenter au besoin)
    # ------------------------------------------------------------------ #
    # logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Retourne un logger structlog lié au nom donné.

    :param name: Nom du logger (typiquement ``__name__``).
    :return: Logger structlog prêt à l'emploi.
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- #
# Démo : python -m mubawab_scraper.logging_conf
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    setup_logging(
        "DEBUG",
        log_dir="./logs",  # ← stockage activé
        rotation="size",
        max_bytes=1_000_000,  # 1 Mo (pour tester la rotation)
        backup_count=3,
        console=True,
    )
    log = get_logger(__name__)

    log.info("app_started", version="0.1.0")
    for i in range(5):
        log.debug("tick", i=i)
    try:
        raise ZeroDivisionError
    except ZeroDivisionError:
        log.exception("boom")
