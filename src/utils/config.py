"""Application configuration.

Using Python for rapid CLI/API development and rich ecosystem (FastAPI, Typer).
"""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from .env and environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    hf_api_token: str = Field(
        default="",
        validation_alias=AliasChoices("HF_API_TOKEN", "HUGGING_FACE_API_KEY"),
    )
    database_url: str = Field(
        default="postgresql+psycopg://jira:change_me@localhost:5432/jira_plus_plus",
        validation_alias=AliasChoices("DATABASE_URL"),
    )
    plantuml_server_url: str = "https://www.plantuml.com/plantuml/png/"
    mermaid_renderer_image: str = "minlag/mermaid-cli"
    structurizr_renderer_image: str = "archviz-structurizr-renderer:latest"
    output_dir: str = "outputs"
    default_diagram_type: str = "sequence"
    enable_ir: bool = True  # Enable IR pipeline by default
    enable_ir_enrichment: bool = True  # Use enriched IR payloads when available


settings = Settings()
