from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    data_dir: Path = Field(default=Path(".project-helper-data"), alias="PROJECT_HELPER_DATA_DIR")
    allowed_hosts: str = Field(default="github.com,www.github.com", alias="PROJECT_HELPER_ALLOWED_HOSTS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def clone_dir(self) -> Path:
        return self.data_dir / "repos"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "project_helper.sqlite3"

    @property
    def allowed_host_set(self) -> set[str]:
        return {host.strip().lower() for host in self.allowed_hosts.split(",") if host.strip()}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.clone_dir.mkdir(parents=True, exist_ok=True)
    return settings
