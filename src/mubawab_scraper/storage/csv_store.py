"""
Module d'export des données.

Ce module fournit deux points d'entrée principaux :

- :func:`export`       — exporte la table ``listings`` (annonces) dans le
  format choisi (csv, parquet ou json).
- :func:`export_villes` — exporte la table ``villes`` (villes scrapées) en CSV.

Chaque export est écrit dans un sous-dossier daté (et horodaté par défaut)
afin d'éviter tout écrasement entre deux exécutions. La structure produite
est de la forme ::

    <settings.export_dir>/
    └── 2026-10-13_14-32-07/
        ├── mubawab_export_2026-10-13_14-32-07.csv
        └── mubawab_villes_2026-10-13_14-32-07.csv

Les noms de fichiers et de dossiers utilisent des tirets et underscores
(``-``, ``_``) plutôt que des deux-points pour rester compatibles avec
Windows, macOS et Linux.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

import pandas as pd

from mubawab_scraper.config import settings


# --------------------------------------------------------------------------- #
# Helpers internes
# --------------------------------------------------------------------------- #

def _query(sql: str) -> pd.DataFrame:
    """
    Exécute une requête SQL sur la base SQLite et renvoie le résultat
    sous forme de :class:`pandas.DataFrame`.

    La connexion est fermée automatiquement en sortie de bloc grâce à
    :func:`contextlib.closing` (le gestionnaire de contexte natif de
    ``sqlite3.Connection`` commit/rollback mais ne ferme pas la connexion).

    :param sql: Requête SQL à exécuter (SELECT).
    :return: DataFrame contenant les lignes retournées.
    """
    with closing(sqlite3.connect(settings.db_path)) as conn:
        return pd.read_sql_query(sql, conn)


def _dated_dir(base: Path, with_time: bool = False) -> Path:
    """
    Crée (si nécessaire) et renvoie un sous-dossier daté sous ``base``.

    :param base: Dossier racine d'export (ex. ``settings.export_dir``).
    :param with_time: Si ``True``, ajoute l'heure au nom du dossier
        (format ``YYYY-MM-DD_HH-MM-SS``) afin qu'une exécution = un dossier.
        Si ``False``, un seul dossier par jour (``YYYY-MM-DD``) est utilisé
        et les exécutions suivantes du même jour écrasent les fichiers.
    :return: Chemin du dossier créé (ou déjà existant).
    """
    fmt = "%Y-%m-%d_%H-%M-%S" if with_time else "%Y-%m-%d"
    stamp = datetime.now(timezone.utc).strftime(fmt)
    out_dir = base / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# --------------------------------------------------------------------------- #
# API publique
# --------------------------------------------------------------------------- #

def export(fmt: str = "csv", *, with_time: bool = True) -> str:
    """
    Exporte la table ``listings`` dans le format demandé.

    Le fichier est écrit dans un sous-dossier horodaté de
    ``settings.export_dir``. Le nom du fichier reprend le même horodatage
    que le dossier pour faciliter la traçabilité.

    Formats supportés :

    - ``"csv"``     : encodage UTF-8 avec BOM (``utf-8-sig``) pour une
      ouverture correcte des accents dans Excel.
    - ``"parquet"`` : nécessite ``pyarrow`` (ou ``fastparquet``).
    - ``"json"``    : un tableau d'objets (``orient="records"``), Unicode
      préservé, indentation lisible.

    :param fmt: Format d'export — ``"csv"``, ``"parquet"`` ou ``"json"``.
    :param with_time: Horodatage à la seconde (``True``) ou au jour (``False``).
    :return: Chemin absolu ou relatif du fichier écrit, sous forme de chaîne.
    :raises ValueError: Si ``fmt`` n'est pas un format supporté.
    """
    base_dir = Path(settings.export_dir)
    out_dir = _dated_dir(base_dir, with_time=with_time)
    df = _query("SELECT * FROM listings")

    stamp = out_dir.name
    path = out_dir / f"mubawab_export_{stamp}.{fmt}"

    match fmt:
        case "csv":
            # utf-8-sig ajoute le BOM : Excel (Windows) détecte ainsi l'UTF-8.
            df.to_csv(path, index=False, encoding="utf-8-sig")
        case "parquet":
            df.to_parquet(path, index=False)
        case "json":
            df.to_json(
                path,
                orient="records",
                force_ascii=False,
                indent=2,
            )
        case _:
            raise ValueError(f"Format non supporté: {fmt}")

    return str(path)


def export_raw(fmt: str = "csv", *, with_time: bool = True) -> str:
    """Export raw, unnormalized listing-card records from SQLite."""
    if fmt not in {"csv", "parquet", "json"}:
        raise ValueError(f"Format non supporté: {fmt}")

    out_dir = _dated_dir(Path(settings.export_dir), with_time=with_time)
    df = _query("SELECT * FROM raw_listings ORDER BY city, transaction_type, ad_id")
    path = out_dir / f"mubawab_raw_export_{out_dir.name}.{fmt}"

    match fmt:
        case "csv":
            df.to_csv(path, index=False, encoding="utf-8-sig")
        case "parquet":
            df.to_parquet(path, index=False)
        case "json":
            df.to_json(path, orient="records", force_ascii=False, indent=2)

    return str(path)


def export_raw_bundle(*, with_time: bool = True) -> list[str]:
    """Export raw listing records as both CSV and JSON using one timestamp."""
    out_dir = _dated_dir(Path(settings.export_dir), with_time=with_time)
    df = _query("SELECT * FROM raw_listings ORDER BY city, transaction_type, ad_id")
    stamp = out_dir.name
    csv_path = out_dir / f"mubawab_raw_export_{stamp}.csv"
    json_path = out_dir / f"mubawab_raw_export_{stamp}.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_json(json_path, orient="records", force_ascii=False, indent=2)
    return [str(csv_path), str(json_path)]


def export_raw_details(
    fmt: str = "csv",
    *,
    with_time: bool = True,
) -> list[str]:
    """Export raw listing cards and their detail records."""
    if fmt not in {"csv", "parquet", "json"}:
        raise ValueError(f"Format non supporté: {fmt}")

    out_dir = _dated_dir(Path(settings.export_dir), with_time=with_time)
    listings = _query(
        "SELECT * FROM raw_listings ORDER BY city, transaction_type, ad_id"
    )
    details = _query("SELECT * FROM raw_listing_details ORDER BY ad_id")
    stamp = out_dir.name

    if fmt == "json":
        path = out_dir / f"mubawab_raw_details_export_{stamp}.json"
        payload = {
            "raw_listings": listings.to_dict(orient="records"),
            "raw_listing_details": details.to_dict(orient="records"),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return [str(path)]

    listings_path = out_dir / f"raw_listings_{stamp}.{fmt}"
    details_path = out_dir / f"raw_listing_details_{stamp}.{fmt}"
    if fmt == "csv":
        listings.to_csv(listings_path, index=False, encoding="utf-8-sig")
        details.to_csv(details_path, index=False, encoding="utf-8-sig")
    else:
        listings.to_parquet(listings_path, index=False)
        details.to_parquet(details_path, index=False)
    return [str(listings_path), str(details_path)]


def export_villes(*, with_time: bool = True) -> str:
    """
    Exporte la table ``villes`` en CSV.

    Les colonnes exportées sont ``name``, ``url``, ``link`` et
    ``attrNameurl``, triées par ``name``. Le fichier est écrit dans le
    même type de sous-dossier horodaté que :func:`export`.

    :param with_time: Horodatage à la seconde (``True``) ou au jour (``False``).
    :return: Chemin du fichier CSV écrit, sous forme de chaîne.
    """
    base_dir = Path(settings.export_dir)
    out_dir = _dated_dir(base_dir, with_time=with_time)
    df = _query(
        "SELECT name, url, link, attrNameurl FROM villes ORDER BY name"
    )

    stamp = out_dir.name
    path = out_dir / f"mubawab_villes_{stamp}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return str(path)


# --------------------------------------------------------------------------- #
# Exemple d'utilisation (à retirer ou protéger par __main__)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print(export("csv"))
    print(export("json", with_time=False))
    print(export_villes())