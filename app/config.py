from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://localhost:8000"
    db_path: Path = Path("data/inventory.db")
    photo_dir: Path = Path("data/photos")
    secret_key: str = "dev-secret-change-me"
    session_max_age: int = 12 * 60 * 60

    @property
    def db_file(self) -> Path:
        path = self.db_path
        return path if path.is_absolute() else PROJECT_DIR / path

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_file}"

    @property
    def photo_root(self) -> Path:
        path = self.photo_dir
        return path if path.is_absolute() else PROJECT_DIR / path

    def prepare_dirs(self) -> None:
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self.photo_root.mkdir(parents=True, exist_ok=True)


settings = Settings()
