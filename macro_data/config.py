"""Config: load .env, resolve paths, expose API keys.

Single source of truth for credentials and where data lands. Keys live only in
.env (gitignored); nothing else reads them.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Output directory for saved CSVs. Override with DATA_DIR in .env if you like.
DATA_DIR = Path(os.getenv("DATA_DIR") or ROOT / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def key(name: str) -> str:
    """Return an API key from the environment, or raise a clear error."""
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Missing {name}. Add it to {ROOT / '.env'} (see .env.example)."
        )
    return val