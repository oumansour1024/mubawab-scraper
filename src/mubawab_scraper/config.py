from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MUBAWAB_")
    base_url: str = "https://www.mubawab.ma/fr"
    headless: bool = True
    max_pages: int = Field(default=10, ge=1)
    min_delay: float = 1.5
    max_delay: float = 3.0
    db_path: str = "data/db/mubawab.db"
    export_dir: str = "data/processed"
    log_dir: str = "logs"
    log_level: str = "INFO"
    log_json: bool = False
    log_rotation: str = "size"       # "size" ou "time"
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 7

settings = Settings()