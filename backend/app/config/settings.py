import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Build an absolute path to the .env file in the project root.
# This makes the settings loading independent of the current working directory.
# Path(__file__) is .../csv_mvp/app/config/settings.py
# .parent.parent.parent is .../csv_mvp/
try:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
except NameError:
    # If __file__ is not defined (e.g., in a Jupyter notebook or interactive interpreter)
    # fall back to the current working directory.
    env_path = Path.cwd() / ".env"


class Settings(BaseSettings):
    """
    Application settings loaded from the .env file.
    """
    ANTHROPIC_API_KEY: str

    # Supabase credentials
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # Stripe credentials
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_PRO_PRICE_ID: str # Add this for the Pro plan price ID
    WEBHOOK_SECRET: str

    model_config = SettingsConfigDict(env_file=env_path, env_file_encoding="utf-8", extra="ignore")


settings = Settings()