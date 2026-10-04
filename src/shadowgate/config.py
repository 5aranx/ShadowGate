from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHADOWGATE_", env_file=".env")

    db_path: str = "shadowgate.db"
    data_dir: str = ".shadowgate"
    host: str = "127.0.0.1"
    port: int = 8080
    insecure_dev: bool = False
    audit_log_path: str = ".shadowgate/audit.log"
    org_key_path: str = ".shadowgate/org_ed25519.key"
    ca_key_path: str = ".shadowgate/ca.key"
    ca_cert_path: str = ".shadowgate/ca.crt"


@lru_cache
def get_settings() -> Settings:
    return Settings()
