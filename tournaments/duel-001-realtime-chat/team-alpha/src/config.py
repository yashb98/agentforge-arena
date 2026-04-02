"""Application configuration."""
from __future__ import annotations
import os

DATABASE_URL: str = os.getenv("DATABASE_URL", "chat.db")
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
