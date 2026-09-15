from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

if sys.platform == "win32":
    # Lokalni Windows fix za SSL presretanje (antivirus/korporativna mreža) — vidi requirements.txt.
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def telegram_credentials() -> tuple[str, str]:
    return os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")


def gemini_credentials() -> str:
    return os.environ.get("GEMINI_API_KEY", "")
