from contextlib import closing
import sqlite3
from pathlib import Path

import pandas as pd
from mubawab_scraper.config import settings

def export(fmt: str = "csv") -> str:
    out_dir = Path(settings.export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(settings.db_path)) as conn:
        df = pd.read_sql_query("SELECT * FROM listings", conn)

    path = out_dir / f"mubawab_export.{fmt}"
    match fmt:
        case "csv":     df.to_csv(path, index=False, encoding="utf-8-sig")
        case "parquet": df.to_parquet(path, index=False)
        case "json":    df.to_json(path, orient="records", force_ascii=False, indent=2)
        case _:         raise ValueError(f"Format non supporté: {fmt}")
    return str(path)


def export_villes() -> str:
    out_dir = Path(settings.export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(settings.db_path)) as conn:
        df = pd.read_sql_query(
            "SELECT name, url, link, attrNameurl FROM villes ORDER BY name",
            conn,
        )

    path = out_dir / "mubawab_villes.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return str(path)