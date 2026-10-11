from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MUBAWAB_")
    base_url: str = "https://www.mubawab.ma/fr"
    headless: bool = True
    max_pages: int = Field(default=10, ge=1)
    min_delay: float = 1.5
    max_delay: float = 3.0
    page_timeout: int = 15
    db_path: str = "data/db/mubawab.db"
    export_dir: str = "data/processed"
    log_level: str = "INFO"

settings = Settings()