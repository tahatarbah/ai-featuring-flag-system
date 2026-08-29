from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/aiflags"
    admin_token: str = "dev-admin-token"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    ollama_judge_model: str = "llama3.2"
    demo_mock_llm: bool = True
    sdk_dev_key: str = "sdk_dev_warden_local"
    gate_enabled: bool = True
    gate_interval_seconds: int = 15
    gate_window_minutes: int = 15
    config_poll_seconds: int = 10


settings = Settings()
